"""Draft feedback tracker — learns from edits to email drafts."""

from __future__ import annotations

import Levenshtein

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)


async def track_edit(
    draft_id: int,
    original_body: str,
    edited_body: str,
    sender_domain: str | None = None,
    category: str | None = None,
) -> dict:
    """Track an edit to a draft as a learning signal.

    Computes edit distance and ratio, stores in draft_feedback table.
    """
    edit_distance = Levenshtein.distance(original_body, edited_body)
    max_len = max(len(original_body), len(edited_body), 1)
    edit_ratio = edit_distance / max_len

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Update the draft with edited body
        await conn.execute(
            "UPDATE email_drafts SET edited_body = $1, status = 'edited' WHERE id = $2",
            edited_body,
            draft_id,
        )

        # Store feedback
        await conn.execute(
            """
            INSERT INTO draft_feedback
                (draft_id, sender_domain, category, edit_distance, edit_ratio,
                 original_length, edited_length)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            draft_id,
            sender_domain,
            category,
            edit_distance,
            edit_ratio,
            len(original_body),
            len(edited_body),
        )

    log.info(
        "draft_edit_tracked",
        draft_id=draft_id,
        edit_distance=edit_distance,
        edit_ratio=round(edit_ratio, 3),
        sender_domain=sender_domain,
    )

    return {
        "draft_id": draft_id,
        "edit_distance": edit_distance,
        "edit_ratio": round(edit_ratio, 3),
    }
