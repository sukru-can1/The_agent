"""Freshdesk API client — ticket management integration."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.settings import get_settings
from agent1.integrations._base import BaseAPIClient

STATUS_MAP: dict[str, int] = {
    "open": 2,
    "pending": 3,
    "resolved": 4,
    "closed": 5,
}

PRIORITY_MAP: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "urgent": 4,
}


class FreshdeskClient(BaseAPIClient):
    _integration_name = "Freshdesk"

    @property
    def available(self) -> bool:
        return bool(get_settings().freshdesk_api_key)

    def _build_client(self) -> httpx.AsyncClient:
        settings = get_settings()
        return httpx.AsyncClient(
            base_url=f"https://{settings.freshdesk_domain}/api/v2",
            auth=(settings.freshdesk_api_key, "X"),
            timeout=30.0,
        )

    # -- Typed convenience methods -------------------------------------------

    async def get_tickets(self, **params: Any) -> Any:
        return await self.get("/tickets", params=params or None)

    async def get_ticket(self, ticket_id: int, *, include: str = "conversations") -> Any:
        return await self.get(f"/tickets/{ticket_id}", params={"include": include})

    async def add_note(self, ticket_id: int, body: str, *, private: bool = True) -> Any:
        return await self.post(
            f"/tickets/{ticket_id}/notes",
            json={"body": body, "private": private},
        )

    async def update_ticket(self, ticket_id: int, **fields: Any) -> Any:
        return await self.put(f"/tickets/{ticket_id}", json=fields)
