# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_DIR = REPO_ROOT / "intel_owl" / "settings"
CHAT_TASK = "api_app.chatbot_manager.tasks.process_chat_message"

# Settings are read at import time, so the effect of an environment variable can only be observed
# in a freshly booted interpreter: override_settings would assign the value we are trying to prove
# is computed, and reloading the settings package in-process corrupts it for every other test.
# This probe reports what a real deployment would end up with, from the setting down to the queue
# the chat task is actually routed to.
SETTINGS_PROBE = """
import json

import django

django.setup()

from django.conf import settings
from intel_owl.celery import app, get_queue_name

print(
    json.dumps(
        {
            "chatbot_queue": settings.CHATBOT_QUEUE,
            "celery_queues": settings.CELERY_QUEUES,
            "routed_queue": app.conf.task_routes["%s"]["queue"],
            "declared_queues": [queue.name for queue in app.conf.task_queues],
            "expected_queue_name": get_queue_name(settings.CHATBOT_QUEUE),
        }
    )
)
"""


class ChatbotQueueSettingTestCase(SimpleTestCase):
    """The chatbot queue name must be configurable end to end: whatever the environment says has
    to reach ``settings.CHATBOT_QUEUE`` *and* the Celery route of the chat task, otherwise turns
    are published to a queue no worker drains."""

    def _boot_settings(self, chatbot_queue: Optional[str] = None) -> Dict:
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "intel_owl.settings"
        if chatbot_queue is None:
            env.pop("CHATBOT_QUEUE", None)
        else:
            env["CHATBOT_QUEUE"] = chatbot_queue
        result = subprocess.run(
            [sys.executable, "-c", SETTINGS_PROBE % CHAT_TASK],
            capture_output=True,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"settings probe crashed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        # django.setup() is free to log on the way up, so only the last line is the payload
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_custom_chatbot_queue_reaches_settings_and_task_routing(self):
        booted = self._boot_settings(chatbot_queue="my_custom_queue")

        self.assertEqual(booted["chatbot_queue"], "my_custom_queue")
        self.assertIn("my_custom_queue", booted["celery_queues"])
        # get_queue_name appends .fifo under SQS, so compare against what the deployment derives
        self.assertEqual(booted["routed_queue"], booted["expected_queue_name"])
        self.assertIn(
            booted["expected_queue_name"],
            booted["declared_queues"],
            msg="the chat task is routed to a queue that is never declared",
        )

    def test_chatbot_queue_falls_back_to_the_default_when_unset_or_blank(self):
        for chatbot_queue in (None, ""):
            with self.subTest(chatbot_queue=chatbot_queue):
                booted = self._boot_settings(chatbot_queue=chatbot_queue)

                self.assertEqual(booted["chatbot_queue"], "chatbot")
                self.assertIn("chatbot", booted["celery_queues"])


def _assigned_names(node: ast.AST) -> Iterator[Tuple[str, int]]:
    """Names bound by a module-level assignment, including inside if/try blocks (where settings are
    conditionally defined). Function and class bodies are skipped: their locals are not settings."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    yield target.id, child.lineno
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            yield child.target.id, child.lineno
        yield from _assigned_names(child)


def _wildcard_imported_modules() -> List[str]:
    tree = ast.parse((SETTINGS_DIR / "__init__.py").read_text())
    return [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]


class SettingsSingleSourceTestCase(SimpleTestCase):
    """intel_owl/settings/__init__.py pulls every submodule in with a wildcard import, so a name
    assigned in two of them silently resolves to whichever module is imported last. Re-ordering
    those lines then changes the deployment's behaviour, which is exactly how CHATBOT_QUEUE ended
    up ignoring its environment variable. One assignment per setting removes the ordering
    dependency altogether."""

    def test_no_setting_is_assigned_in_two_wildcard_imported_modules(self):
        origins: Dict[str, Set[str]] = defaultdict(set)
        for module in _wildcard_imported_modules():
            module_path = SETTINGS_DIR / f"{module}.py"
            for name, lineno in _assigned_names(ast.parse(module_path.read_text())):
                origins[name].add(f"{module}.py:{lineno}")

        shadowed = {
            name: sorted(locations)
            for name, locations in origins.items()
            # locations within a single module are re-assignments, not shadowing
            if len({location.split(":")[0] for location in locations}) > 1
        }

        self.assertEqual(
            shadowed,
            {},
            msg="these settings are assigned in more than one wildcard-imported module, so their "
            "value depends on the import order in intel_owl/settings/__init__.py",
        )
