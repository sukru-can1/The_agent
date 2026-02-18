"""StarInfinity poller — checks for overdue tasks."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_starinfinity() -> None:
    """Check StarInfinity for overdue tasks and publish events for each."""
    settings = get_settings()

    if not settings.starinfinity_base_url or not settings.starinfinity_api_key:
        log.debug("starinfinity_poll_skipped", reason="not_configured")
        return

    log.debug("starinfinity_poll_started")

    now_iso = datetime.now(UTC).isoformat()

    try:
        async with httpx.AsyncClient(
            base_url=settings.starinfinity_base_url,
            headers={"Authorization": f"Bearer {settings.starinfinity_api_key}"},
            timeout=30.0,
        ) as client:
            resp = await client.get(
                "/api/tasks",
                params={"due_before": now_iso, "status": "open"},
            )
            resp.raise_for_status()
            data = resp.json()

    except httpx.HTTPStatusError as exc:
        log.warning(
            "starinfinity_poll_api_error",
            status_code=exc.response.status_code,
            detail=exc.response.text[:500],
        )
        return
    except httpx.HTTPError as exc:
        log.warning("starinfinity_poll_network_error", error=str(exc))
        return

    # Normalize: response may be a list or a dict with a tasks/data key
    tasks: list[dict] = []
    if isinstance(data, list):
        tasks = data
    elif isinstance(data, dict):
        tasks = data.get("tasks", data.get("data", []))

    published = 0

    for task in tasks:
        task_id = str(task.get("id", ""))
        if not task_id:
            continue

        due_date = task.get("due_date", "")
        dedup_identifier = f"{task_id}:{due_date}"

        # Skip already-processed overdue task events
        if await is_duplicate("starinfinity", dedup_identifier):
            continue

        idempotency_key = f"starinfinity:overdue:{task_id}:{due_date}"

        event = Event(
            source=EventSource.STARINFINITY,
            event_type="task_overdue",
            priority=Priority.HIGH,
            payload={
                "task_id": task_id,
                "title": task.get("title", ""),
                "assignee": task.get("assignee", ""),
                "due_date": due_date,
                "project_id": task.get("project_id", ""),
            },
            idempotency_key=idempotency_key,
        )

        await publish_event(event)
        await mark_processed("starinfinity", dedup_identifier)
        published += 1

        log.info(
            "starinfinity_overdue_task_event",
            task_id=task_id,
            title=task.get("title", "")[:80],
            due_date=due_date,
        )

    log.debug(
        "starinfinity_poll_completed",
        overdue_tasks_found=len(tasks),
        events_published=published,
    )
