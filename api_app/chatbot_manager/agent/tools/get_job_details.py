# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

import json

from langchain_core.tools import tool


def make_get_job_details_tool(user):
    # Built per-request and closed over `user`, so the lookup is hard-scoped to that
    # user's jobs (multi-tenancy enforced here). LangChain requires a tool to return a
    # string for the ReAct "Observation" step, so we return a JSON-serialized envelope.
    @tool("get_job_details")
    def get_job_details(job_id: int) -> str:
        """Get full details of an IntelOwl job by its numeric ID.

        Args:
            job_id: The numeric ID of the job to retrieve.

        Returns:
            JSON string with shape {"errors": [...], "job": {...} | null}.
        """
        from api_app.models import Job

        try:
            job = (
                Job.objects.select_related("analyzable")
                .prefetch_related("analyzer_reports__config", "analyzers_to_execute", "tags")
                .get(pk=job_id, user=user)
            )
        except Job.DoesNotExist:
            return json.dumps({"errors": [f"Job with ID {job_id} not found or not accessible."], "job": None})

        analyzer_reports = []
        for report in job.analyzer_reports.all():
            # `report.report` is a JSONField (dict / list / scalar depending on the
            # analyzer). Dicts pass through and get re-serialized below; anything else is
            # stringified and truncated to cap the size fed into the LLM prompt.
            analyzer_reports.append(
                {
                    "name": report.config.name,
                    "status": report.status,
                    "report": report.report if isinstance(report.report, dict) else str(report.report)[:500],
                }
            )

        return json.dumps(
            {
                "errors": [],
                "job": {
                    "id": job.pk,
                    "observable_name": job.analyzable.name,
                    "observable_classification": job.analyzable.classification,
                    "md5": job.analyzable.md5,
                    "status": job.status,
                    "tlp": job.tlp,
                    "received_request_time": str(job.received_request_time),
                    "finished_analysis_time": str(job.finished_analysis_time)
                    if job.finished_analysis_time
                    else None,
                    "process_time": job.process_time,
                    "analyzers_to_execute": list(job.analyzers_to_execute.values_list("name", flat=True)),
                    "tags": list(job.tags.values_list("label", flat=True)),
                    "errors": job.errors,
                    "warnings": job.warnings,
                    "analyzer_reports": analyzer_reports,
                },
            },
            indent=2,
        )

    return get_job_details
