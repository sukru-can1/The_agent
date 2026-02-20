"""MCP server discovery — find and propose new tool integrations."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.intelligence.proposals import create_proposal, ProposalType

log = get_logger(__name__)


async def search_mcp_registries(capability: str) -> list[dict]:
    """Search MCP registries for servers matching a capability description.

    Searches Smithery.ai and returns top matches.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Smithery.ai registry search
            response = await client.get(
                "https://registry.smithery.ai/servers",
                params={"q": capability, "limit": 5},
            )
            if response.status_code == 200:
                data = response.json()
                return [
                    {
                        "name": s.get("qualifiedName", s.get("name", "")),
                        "description": s.get("description", ""),
                        "url": s.get("homepage", ""),
                    }
                    for s in data.get("servers", [])[:3]
                ]
    except Exception:
        log.warning("mcp_registry_search_failed", capability=capability)

    return []


async def propose_mcp_server(
    name: str,
    description: str,
    config: dict,
    reason: str,
) -> None:
    """Create a proposal to connect a new MCP server."""
    await create_proposal(
        type=ProposalType.MCP_SERVER,
        title=f"Connect MCP: {name}",
        description=f"{description}\n\nReason: {reason}",
        config=config,
        confidence=0.5,
    )
    log.info("mcp_server_proposed", name=name)
