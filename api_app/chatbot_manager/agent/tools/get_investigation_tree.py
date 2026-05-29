# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

from langchain_core.tools import tool

# Bounds for the LLM-facing tree: keep the serialized payload small enough not to blow up
# the prompt regardless of how large an investigation is.
_MAX_DEPTH = 10
_MAX_NODES = 200


def _compact_node(job) -> dict:
    """Minimal LLM-facing view of a job node: id, observable, status, children."""
    return {
        "id": job.pk,
        "observable": getattr(job.analyzable, "name", None),
        "status": job.status,
        "children": [],
    }


def _build_tree(investigation) -> dict:
    """Assemble a compact nested tree for an investigation, avoiding the treebeard N+1.

    A Job is a treebeard ``MP_Node``; walking it with ``get_children()`` recursively would
    fire one query per node. Instead we fetch each root's whole subtree with a single
    ``get_descendants()`` call and rebuild the nesting in Python from treebeard's
    materialized ``path`` (a child's parent path is its own path minus the last step), so
    there are no per-node queries. Depth and node count are capped to bound the payload.
    """
    payload = {
        "id": investigation.pk,
        "name": investigation.name,
        "status": investigation.status,
        "jobs": [],
    }
    remaining = _MAX_NODES
    truncated = False

    # `investigation.jobs` are the root jobs; their descendants live only in the tree.
    for root in investigation.jobs.select_related("analyzable"):
        if remaining <= 0:
            truncated = True
            break
        root_node = _compact_node(root)
        payload["jobs"].append(root_node)
        remaining -= 1
        # Map path -> node for every kept node, to link children to parents in O(1).
        by_path = {root.path: root_node}

        # One query for the whole subtree, in path order (treebeard pre-order DFS), so a
        # parent is always processed before its children.
        for job in root.get_descendants().select_related("analyzable").order_by("path"):
            if (job.depth - root.depth) > _MAX_DEPTH:
                continue
            parent = by_path.get(job.path[: -job.steplen])
            if parent is None:
                # Ancestor was capped out (depth/budget); skip to avoid orphaning.
                continue
            if remaining <= 0:
                truncated = True
                break
            node = _compact_node(job)
            by_path[job.path] = node
            parent["children"].append(node)
            remaining -= 1

    if truncated:
        payload["truncated"] = True
    return payload


def make_get_investigation_tree_tool(user):
    # Built per-request and closed over `user`. The lookup is scoped with
    # `visible_for_user` (owned + organization-shared investigations), so the LLM cannot
    # reach an investigation the user can't see. Returns a string for the ReAct
    # "Observation": a JSON-serialized envelope.
    @tool("get_investigation_tree")
    def get_investigation_tree(investigation_id: int) -> str:
        """Get the job tree of an IntelOwl investigation by its numeric ID.

        Returns the investigation with its jobs as a nested tree (each node: id,
        observable, status, children). Depth and node count are capped for large trees
        (a `"truncated": true` flag is added when the cap is hit).

        Args:
            investigation_id: The numeric ID of the investigation.

        Returns:
            JSON string with shape {"errors": [...], "investigation": {...} | null}.
        """
        from api_app.chatbot_manager.serializers import InvestigationTreeResultSerializer
        from api_app.investigations_manager.models import Investigation

        try:
            investigation = Investigation.objects.visible_for_user(user).get(pk=investigation_id)
        except Investigation.DoesNotExist:
            return InvestigationTreeResultSerializer(
                {
                    "errors": [f"Investigation with ID {investigation_id} not found or not accessible."],
                    "investigation": None,
                }
            ).to_json()

        return InvestigationTreeResultSerializer(
            {"errors": [], "investigation": _build_tree(investigation)}
        ).to_json()

    return get_investigation_tree
