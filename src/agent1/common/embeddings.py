"""Voyage AI embedding client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voyageai

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    return _client


async def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text string."""
    client = _get_client()
    settings = get_settings()
    result = await client.embed([text], model=settings.voyage_model)
    return result.embeddings[0]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts (batched)."""
    if not texts:
        return []
    client = _get_client()
    settings = get_settings()
    result = await client.embed(texts, model=settings.voyage_model)
    return result.embeddings
