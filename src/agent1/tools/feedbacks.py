"""Feedbacks app integration tools — REST API access to survey.glamira.com."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Feedbacks API not configured — set feedbacks_api_key"}


def _get_client() -> httpx.AsyncClient | None:
    """Create an httpx client for the Feedbacks API.

    Returns None if feedbacks_api_key is not set.
    """
    settings = get_settings()
    if not settings.feedbacks_api_key:
        return None
    return httpx.AsyncClient(
        base_url=settings.feedbacks_api_url,
        headers={"Authorization": f"Bearer {settings.feedbacks_api_key}"},
        timeout=30.0,
    )


def _unwrap(data: Any) -> Any:
    """Strip the standard API envelope {app, timestamp, data} if present."""
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


class FeedbacksGetInsightsTool(BaseTool):
    name = "feedbacks_get_insights"
    description = (
        "Get trend analysis and anomaly alerts from the feedbacks system. "
        "Returns CSAT trends, response rate changes, and alert details by severity."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 7, "description": "Analysis period in days"},
            "threshold": {
                "type": "number",
                "description": "Alert sensitivity threshold (0-1, lower = more alerts)",
            },
            "min_sample": {
                "type": "integer",
                "description": "Minimum sample size for statistical significance",
            },
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        params: dict[str, Any] = {}
        if "days" in kwargs:
            params["days"] = kwargs["days"]
        if "threshold" in kwargs:
            params["threshold"] = kwargs["threshold"]
        if "min_sample" in kwargs:
            params["minSample"] = kwargs["min_sample"]

        try:
            async with client:
                resp = await client.get("/insights", params=params)
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksGetOverviewTool(BaseTool):
    name = "feedbacks_get_overview"
    description = "Get a high-level overview of all feedbacks modules: surveys, Trustpilot, tasks."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        try:
            async with client:
                resp = await client.get("/overview")
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksGetTrustpilotReviewsTool(BaseTool):
    name = "feedbacks_get_trustpilot_reviews"
    description = (
        "Get Trustpilot reviews with filtering. "
        "Includes star rating, defendability analysis, generated responses."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "max_stars": {
                "type": "integer",
                "description": "Maximum stars filter (e.g., 2 for negative reviews)",
            },
            "status": {
                "type": "string",
                "description": "Review status filter (new, responded, etc.)",
            },
            "limit": {"type": "integer", "default": 20, "description": "Max reviews to return"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        params: dict[str, Any] = {}
        if "max_stars" in kwargs:
            params["maxStars"] = kwargs["max_stars"]
        if "status" in kwargs:
            params["status"] = kwargs["status"]
        if "limit" in kwargs:
            params["limit"] = kwargs["limit"]

        try:
            async with client:
                resp = await client.get("/trustpilot/reviews", params=params)
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksGetTasksTool(BaseTool):
    name = "feedbacks_get_tasks"
    description = "Get task counts and details from the feedbacks system (complaints, follow-ups)."
    input_schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by task status (new, in_progress, done)",
            },
            "type": {"type": "string", "description": "Filter by task type (complaint, follow_up)"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        params: dict[str, Any] = {}
        if "status" in kwargs:
            params["status"] = kwargs["status"]
        if "type" in kwargs:
            params["type"] = kwargs["type"]

        try:
            async with client:
                resp = await client.get("/tasks", params=params)
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksGetSurveyResponsesTool(BaseTool):
    name = "feedbacks_get_survey_responses"
    description = "Get paginated survey responses for a specific survey by ID."
    input_schema = {
        "type": "object",
        "properties": {
            "survey_id": {"type": "string", "description": "Survey ID to fetch responses for"},
            "page": {"type": "integer", "description": "Page number for pagination"},
            "limit": {"type": "integer", "default": 20, "description": "Results per page"},
        },
        "required": ["survey_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        survey_id = kwargs["survey_id"]
        params: dict[str, Any] = {}
        if "page" in kwargs:
            params["page"] = kwargs["page"]
        if "limit" in kwargs:
            params["limit"] = kwargs["limit"]

        try:
            async with client:
                resp = await client.get(f"/surveys/{survey_id}/responses", params=params)
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksStartAutoReporterTool(BaseTool):
    name = "feedbacks_start_auto_reporter"
    description = "Start the auto-reporter to generate and send feedback reports."
    input_schema = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of reports to generate (default: all pending)",
            },
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        body: dict[str, Any] = {}
        if "count" in kwargs:
            body["count"] = kwargs["count"]

        try:
            async with client:
                resp = await client.post("/actions/auto-reporter-start", json=body)
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}


class FeedbacksTriggerTrustpilotSyncTool(BaseTool):
    name = "feedbacks_trigger_trustpilot_sync"
    description = "Trigger a manual sync of Trustpilot reviews into the feedbacks system."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = _get_client()
        if client is None:
            return _NOT_CONFIGURED

        try:
            async with client:
                resp = await client.post("/actions/trustpilot-sync", json={})
                resp.raise_for_status()
                return _unwrap(resp.json())
        except httpx.HTTPStatusError as exc:
            return {"error": f"Feedbacks API error {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}
