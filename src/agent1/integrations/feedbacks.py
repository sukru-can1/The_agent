"""Feedbacks API client — survey.glamira.com REST integration."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.settings import get_settings
from agent1.integrations._base import BaseAPIClient


class FeedbacksClient(BaseAPIClient):
    _integration_name = "Feedbacks"

    @property
    def available(self) -> bool:
        return bool(get_settings().feedbacks_api_key)

    def _build_client(self) -> httpx.AsyncClient:
        settings = get_settings()
        return httpx.AsyncClient(
            base_url=settings.feedbacks_api_url,
            headers={"Authorization": f"Bearer {settings.feedbacks_api_key}"},
            timeout=30.0,
        )

    def _unwrap(self, data: Any) -> Any:
        """Strip the standard API envelope {app, timestamp, data} if present."""
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    # -- Typed convenience methods -------------------------------------------

    async def get_insights(self, **params: Any) -> Any:
        return await self.get("/insights", params=params or None)

    async def get_overview(self) -> Any:
        return await self.get("/overview")

    async def get_trustpilot_reviews(self, **params: Any) -> Any:
        return await self.get("/trustpilot/reviews", params=params or None)

    async def get_tasks(self, **params: Any) -> Any:
        return await self.get("/tasks", params=params or None)

    async def get_survey_responses(self, survey_id: str, **params: Any) -> Any:
        return await self.get(f"/surveys/{survey_id}/responses", params=params or None)

    async def start_auto_reporter(self, **body: Any) -> Any:
        return await self.post("/actions/auto-reporter-start", json=body or None)

    async def trigger_trustpilot_sync(self) -> Any:
        return await self.post("/actions/trustpilot-sync", json={})

    async def get_trustpilot_summary(self) -> Any:
        return await self.get("/trustpilot")
