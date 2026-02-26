"""Core session logic: resolve, create, load history, store messages, compact, expire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource
from agent1.common.settings import get_settings

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Session key resolution
# ---------------------------------------------------------------------------

def resolve_session_key(event: Event) -> str | None:
    """Derive a session key from the event, or None if sessions don't apply.

    Returns:
        ``gchat:{space}:{thread}`` for GChat (falls back to ``gchat:{space}`` for DMs),
        ``dashboard:{email}`` for Dashboard, or ``None`` for all other sources.
    """
    if event.source == EventSource.GCHAT:
        space = event.payload.get("space", "")
        if not space:
            return None
        thread = event.payload.get("thread", "")
        if thread:
            return f"gchat:{space}:{thread}"
        return f"gchat:{space}"

    if event.source == EventSource.DASHBOARD:
        email = event.payload.get("sender_email", "admin")
        return f"dashboard:{email}"

    return None


# ---------------------------------------------------------------------------
# Create / lookup
# ---------------------------------------------------------------------------

async def get_or_create_session(
    key: str,
    platform: str,
    user_id: str,
    user_name: str,
) -> tuple[UUID, bool]:
    """Find an active session for *key*, or create a new one.

    If the existing session has expired (per platform idle timeout), it is marked
    ``expired`` and a fresh session is created.

    Returns ``(session_id, is_new)``.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, last_active_at, platform FROM sessions"
            " WHERE session_key = $1 AND status = 'active'",
            key,
        )
        if row and not _is_session_expired(row["last_active_at"], row["platform"]):
            return UUID(str(row["id"])), False

        # Expire the stale session (if any)
        if row:
            await conn.execute(
                "UPDATE sessions SET status = 'expired' WHERE id = $1",
                row["id"],
            )
            log.info("session_expired_inline", session_key=key, old_id=str(row["id"]))

        # Create new session
        new_id = await conn.fetchval(
            """
            INSERT INTO sessions (session_key, platform, user_id, user_name)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            key,
            platform,
            user_id,
            user_name,
        )
        log.info("session_created", session_key=key, session_id=str(new_id))
        return UUID(str(new_id)), True


# ---------------------------------------------------------------------------
# Load history
# ---------------------------------------------------------------------------

async def load_session_history(
    session_id: UUID,
    max_messages: int | None = None,
    max_tokens: int | None = None,
) -> list[dict]:
    """Load recent user+assistant messages for this session.

    Returns a list of ``{"role": ..., "content": ...}`` dicts in chronological
    order, suitable for prepending to the LLM messages list.  Oldest messages
    are trimmed first to stay within the token budget.

    A stored session summary (from compaction) is prepended as a system-style
    user message if available.
    """
    settings = get_settings()
    if max_messages is None:
        max_messages = settings.session_max_history_messages
    if max_tokens is None:
        max_tokens = settings.session_max_history_tokens

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Grab summary
        summary = await conn.fetchval(
            "SELECT summary FROM sessions WHERE id = $1",
            session_id,
        )

        rows = await conn.fetch(
            """
            SELECT role, content FROM session_messages
            WHERE session_id = $1
              AND role IN ('user', 'assistant')
            ORDER BY created_at ASC
            LIMIT $2
            """,
            session_id,
            max_messages,
        )

    messages: list[dict] = []

    if summary:
        summary_msg = f"[Session summary of earlier conversation]\n{summary}"
        messages.append({"role": "user", "content": summary_msg})
        messages.append({
            "role": "assistant",
            "content": "Understood, I have context from our earlier conversation.",
        })

    for r in rows:
        messages.append({"role": r["role"], "content": r["content"]})

    # Trim oldest to fit rough token budget (1 token ≈ 4 chars)
    total_chars = sum(len(m["content"]) for m in messages)
    char_budget = max_tokens * 4
    while messages and total_chars > char_budget:
        removed = messages.pop(0)
        total_chars -= len(removed["content"])
        # If we removed a user message and the next is assistant (or vice versa),
        # keep removing to maintain alternation
        if messages and messages[0]["role"] == "assistant":
            removed2 = messages.pop(0)
            total_chars -= len(removed2["content"])

    # Ensure alternating user/assistant pattern — must start with user
    while messages and messages[0]["role"] != "user":
        removed = messages.pop(0)
        total_chars -= len(removed["content"])

    # Must end with assistant so next real user message follows naturally
    while messages and messages[-1]["role"] != "assistant":
        messages.pop()

    return messages


# ---------------------------------------------------------------------------
# Store messages
# ---------------------------------------------------------------------------

async def store_session_messages(
    session_id: UUID,
    user_text: str,
    assistant_text: str,
    event_id: UUID | None = None,
) -> None:
    """Persist one exchange (user input + agent response) for the session."""
    if not user_text and not assistant_text:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if user_text:
                await conn.execute(
                    """
                    INSERT INTO session_messages (session_id, role, content, event_id)
                    VALUES ($1, 'user', $2, $3)
                    """,
                    session_id,
                    user_text,
                    event_id,
                )
            if assistant_text:
                await conn.execute(
                    """
                    INSERT INTO session_messages (session_id, role, content, event_id)
                    VALUES ($1, 'assistant', $2, $3)
                    """,
                    session_id,
                    assistant_text,
                    event_id,
                )

            new_count = await conn.fetchval(
                """
                UPDATE sessions
                SET message_count = message_count + $2,
                    last_active_at = NOW()
                WHERE id = $1
                RETURNING message_count
                """,
                session_id,
                (1 if user_text else 0) + (1 if assistant_text else 0),
            )

    settings = get_settings()
    if new_count and new_count >= settings.session_compaction_threshold:
        try:
            await _compact_session(session_id)
        except Exception:
            log.exception("session_compaction_failed", session_id=str(session_id))


# ---------------------------------------------------------------------------
# Compaction — summarise old messages, keep only recent ones
# ---------------------------------------------------------------------------

async def _compact_session(session_id: UUID) -> None:
    """Summarise oldest messages via a flash model, then prune them."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, role, content FROM session_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            """,
            session_id,
        )

    if len(rows) <= 10:
        return

    to_summarise = rows[:-10]
    keep_ids = {r["id"] for r in rows[-10:]}

    # Build text for summarisation
    transcript = "\n".join(f"{r['role']}: {r['content']}" for r in to_summarise)

    # Use flash model for cheap summarisation
    try:
        from agent1.reasoning.providers import get_provider, provider_available
        from agent1.reasoning.router import get_flash_model

        if not await provider_available():
            return

        model = await get_flash_model()
        provider = await get_provider()
        response = await provider.generate(
            model=model,
            messages=[{"role": "user", "content": transcript}],
            max_tokens=300,
            system=(
                "Summarise this conversation between a user and an operations agent "
                "in 2-4 sentences. Focus on key questions asked, decisions made, and "
                "any pending actions. Be concise."
            ),
        )
        summary = (response.text or "").strip()
    except Exception:
        log.exception("session_summary_llm_failed", session_id=str(session_id))
        summary = f"(conversation of {len(to_summarise)} messages)"

    # Persist summary and delete old messages
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE sessions SET summary = $2 WHERE id = $1",
                session_id,
                summary,
            )
            delete_ids = [r["id"] for r in to_summarise]
            await conn.execute(
                "DELETE FROM session_messages WHERE id = ANY($1::bigint[])",
                delete_ids,
            )

    log.info(
        "session_compacted",
        session_id=str(session_id),
        deleted=len(delete_ids),
        kept=len(keep_ids),
    )


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def _is_session_expired(last_active: datetime, platform: str) -> bool:
    """Check whether a session should be considered expired."""
    settings = get_settings()
    now = datetime.now(UTC)

    if platform == "gchat":
        return (now - last_active) > timedelta(minutes=settings.session_idle_timeout_chat_min)

    if platform == "dashboard":
        # Expire after N hours idle, or past the daily 04:00 UTC reset
        if (now - last_active) > timedelta(hours=settings.session_idle_timeout_dashboard_hr):
            return True
        # Daily reset: if last_active was before today's 04:00 UTC and now is after
        reset_today = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if now >= reset_today and last_active < reset_today:
            return True
        return False

    # Unknown platform — don't expire (shouldn't happen)
    return False


async def expire_idle_sessions() -> int:
    """Batch-expire stale active sessions. Returns count expired."""
    settings = get_settings()
    pool = await get_pool()
    now = datetime.now(UTC)

    gchat_cutoff = now - timedelta(minutes=settings.session_idle_timeout_chat_min)
    dashboard_cutoff = now - timedelta(hours=settings.session_idle_timeout_dashboard_hr)
    daily_reset = now.replace(hour=4, minute=0, second=0, microsecond=0)

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE sessions SET status = 'expired'
            WHERE status = 'active'
              AND (
                (platform = 'gchat' AND last_active_at < $1)
                OR (platform = 'dashboard' AND (last_active_at < $2 OR last_active_at < $3))
              )
            """,
            gchat_cutoff,
            dashboard_cutoff,
            daily_reset,
        )

    # asyncpg returns "UPDATE N"
    count = int(result.split()[-1]) if result else 0
    if count:
        log.info("sessions_expired", count=count)
    return count
