# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

from .get_job_details import make_get_job_details_tool
from .search_jobs import make_search_jobs_tool
from .summarize_job import make_summarize_job_tool


def build_tools(user) -> list:
    """Build the agent's tools bound to a single user.

    Each tool is produced by a factory that closes over `user`, so every ORM query the
    agent can run is hard-scoped to that user's data: multi-tenancy is enforced at build
    time and cannot be widened by anything the LLM emits. Every tool returns a string
    (LangChain feeds it back as the ReAct "Observation"); see each tool for its shape.
    """
    return [
        make_search_jobs_tool(user),
        make_get_job_details_tool(user),
        make_summarize_job_tool(user),
    ]
