"""Base API client with shared error handling and lifecycle management."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.logging import get_logger

log = get_logger(__name__)


class IntegrationError(Exception):
    """HTTP integration failure with structured metadata."""

    def __init__(
        self,
        integration: str,
        detail: str,
        status_code: int | None = None,
    ) -> None:
        self.integration = integration
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{integration}: {detail}")


class BaseAPIClient:
    """Async context manager wrapping httpx.AsyncClient with error handling.

    Subclasses must set ``_integration_name`` and implement ``available``
    and ``_build_client()``.  Override ``_unwrap()`` for APIs that wrap
    responses in envelopes.
    """

    _integration_name: str = "unknown"

    @property
    def available(self) -> bool:
        """Return True if the integration is configured and ready."""
        raise NotImplementedError

    def _build_client(self) -> httpx.AsyncClient:
        """Create a configured httpx.AsyncClient (auth, base_url, timeout)."""
        raise NotImplementedError

    def _unwrap(self, data: Any) -> Any:
        """Post-process parsed JSON.  Default: pass-through."""
        return data

    # -- Lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> BaseAPIClient:
        self._client = self._build_client()
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # -- Request helpers -----------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        unwrap: bool = True,
    ) -> Any:
        """Send an HTTP request through the managed client.

        Raises ``IntegrationError`` on HTTP or network failures.
        """
        try:
            resp = await self._client.request(method, path, params=params, json=json)
            resp.raise_for_status()
            data = resp.json()
            return self._unwrap(data) if unwrap else data
        except httpx.HTTPStatusError as exc:
            log.warning(
                f"{self._integration_name.lower()}_api_error",
                status_code=exc.response.status_code,
                detail=exc.response.text[:500],
            )
            raise IntegrationError(
                integration=self._integration_name,
                detail=f"API error {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            log.warning(
                f"{self._integration_name.lower()}_network_error",
                error=str(exc),
            )
            raise IntegrationError(
                integration=self._integration_name,
                detail=str(exc),
            ) from exc

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None, unwrap: bool = True
    ) -> Any:
        return await self.request("GET", path, params=params, unwrap=unwrap)

    async def post(self, path: str, *, json: Any | None = None, unwrap: bool = True) -> Any:
        return await self.request("POST", path, json=json, unwrap=unwrap)

    async def put(self, path: str, *, json: Any | None = None, unwrap: bool = True) -> Any:
        return await self.request("PUT", path, json=json, unwrap=unwrap)
