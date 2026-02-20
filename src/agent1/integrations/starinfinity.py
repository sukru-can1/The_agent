"""StarInfinity API client — project management integration."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.settings import get_settings
from agent1.integrations._base import BaseAPIClient


class StarInfinityClient(BaseAPIClient):
    _integration_name = "StarInfinity"

    @property
    def available(self) -> bool:
        settings = get_settings()
        return bool(settings.starinfinity_base_url and settings.starinfinity_api_key)

    def _build_client(self) -> httpx.AsyncClient:
        settings = get_settings()
        return httpx.AsyncClient(
            base_url=settings.starinfinity_base_url,
            headers={"Authorization": f"Bearer {settings.starinfinity_api_key}"},
            timeout=30.0,
        )

    def _unwrap(self, data: Any) -> Any:
        """Handle list-or-dict response: extract .data if present."""
        if isinstance(data, dict):
            return data.get("data", data)
        return data

    # -- Typed convenience methods -------------------------------------------

    async def list_boards(self) -> Any:
        return await self.get("/boards")

    async def get_items(self, board_id: str, **params: Any) -> Any:
        return await self.get(f"/boards/{board_id}/items", params=params or None)

    async def create_item(self, board_id: str, **body: Any) -> Any:
        return await self.post(f"/boards/{board_id}/items", json=body, unwrap=False)

    async def update_item(self, board_id: str, item_id: str, **body: Any) -> Any:
        return await self.put(f"/boards/{board_id}/items/{item_id}", json=body)
