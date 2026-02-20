"""Feedbacks app integration tools — REST API access to survey.glamira.com."""

from __future__ import annotations

from typing import Any

from agent1.integrations import FeedbacksClient, IntegrationError
from agent1.tools.base import BaseTool

_NOT_CONFIGURED = {"error": "Feedbacks API not configured — set feedbacks_api_key"}


def _error(exc: IntegrationError) -> dict[str, str]:
    """Convert an IntegrationError to a tool-friendly error dict."""
    return {"error": f"Feedbacks API error {exc.status_code}" if exc.status_code else f"Feedbacks: {exc.detail}"}


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
        client = FeedbacksClient()
        if not client.available:
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
                return await client.get_insights(**params)
        except IntegrationError as exc:
            return _error(exc)


class FeedbacksGetOverviewTool(BaseTool):
    name = "feedbacks_get_overview"
    description = "Get a high-level overview of all feedbacks modules: surveys, Trustpilot, tasks."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FeedbacksClient()
        if not client.available:
            return _NOT_CONFIGURED

        try:
            async with client:
                return await client.get_overview()
        except IntegrationError as exc:
            return _error(exc)


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
        client = FeedbacksClient()
        if not client.available:
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
                return await client.get_trustpilot_reviews(**params)
        except IntegrationError as exc:
            return _error(exc)


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
        client = FeedbacksClient()
        if not client.available:
            return _NOT_CONFIGURED

        params: dict[str, Any] = {}
        if "status" in kwargs:
            params["status"] = kwargs["status"]
        if "type" in kwargs:
            params["type"] = kwargs["type"]

        try:
            async with client:
                return await client.get_tasks(**params)
        except IntegrationError as exc:
            return _error(exc)


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
        client = FeedbacksClient()
        if not client.available:
            return _NOT_CONFIGURED

        survey_id = kwargs["survey_id"]
        params: dict[str, Any] = {}
        if "page" in kwargs:
            params["page"] = kwargs["page"]
        if "limit" in kwargs:
            params["limit"] = kwargs["limit"]

        try:
            async with client:
                return await client.get_survey_responses(survey_id, **params)
        except IntegrationError as exc:
            return _error(exc)


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
        client = FeedbacksClient()
        if not client.available:
            return _NOT_CONFIGURED

        body: dict[str, Any] = {}
        if "count" in kwargs:
            body["count"] = kwargs["count"]

        try:
            async with client:
                return await client.start_auto_reporter(**body)
        except IntegrationError as exc:
            return _error(exc)


class FeedbacksTriggerTrustpilotSyncTool(BaseTool):
    name = "feedbacks_trigger_trustpilot_sync"
    description = "Trigger a manual sync of Trustpilot reviews into the feedbacks system."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FeedbacksClient()
        if not client.available:
            return _NOT_CONFIGURED

        try:
            async with client:
                return await client.trigger_trustpilot_sync()
        except IntegrationError as exc:
            return _error(exc)
