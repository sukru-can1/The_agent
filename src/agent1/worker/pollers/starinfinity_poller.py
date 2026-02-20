"""StarInfinity poller — checks for overdue tasks."""

from __future__ import annotations

from datetime import UTC, datetime

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.integrations import IntegrationError, StarInfinityClient
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_starinfinity() -> None:
    """Check StarInfinity for overdue tasks and publish events for each."""
    client = StarInfinityClient()
    if not client.available:
        log.debug("starinfinity_poll_skipped", reason="not_configured")
        return

    log.debug("starinfinity_poll_started")

    try:
        async with client:
            # First, list all boards in the workspace
            boards = await client.list_boards()
            if not isinstance(boards, list):
                boards = []

            if not boards:
                log.debug("starinfinity_poll_no_boards")
                return

            # Check items in each board for overdue tasks
            now = datetime.now(UTC)
            all_overdue: list[dict] = []

            for board in boards:
                board_id = board.get("id")
                if not board_id:
                    continue

                try:
                    items = await client.get_items(board_id, limit=100)
                    if not isinstance(items, list):
                        items = []

                    for item in items:
                        # Check for due date in item values/attributes
                        due_date = _extract_due_date(item)
                        if due_date and due_date < now:
                            item["_board_id"] = board_id
                            item["_board_name"] = board.get("name", "")
                            item["_due_date"] = due_date.isoformat()
                            all_overdue.append(item)

                except IntegrationError:
                    log.debug("starinfinity_board_items_error", board_id=board_id)
                    continue

    except IntegrationError as exc:
        log.warning("starinfinity_poll_error", detail=str(exc))
        return

    published = 0

    for item in all_overdue:
        item_id = str(item.get("id", ""))
        if not item_id:
            continue

        due_date = item.get("_due_date", "")
        dedup_identifier = f"{item_id}:{due_date}"

        if await is_duplicate("starinfinity", dedup_identifier):
            continue

        idempotency_key = f"starinfinity:overdue:{item_id}:{due_date}"

        event = Event(
            source=EventSource.STARINFINITY,
            event_type="task_overdue",
            priority=Priority.HIGH,
            payload={
                "task_id": item_id,
                "board_id": item.get("_board_id", ""),
                "board_name": item.get("_board_name", ""),
                "title": _extract_title(item),
                "due_date": due_date,
            },
            idempotency_key=idempotency_key,
        )

        await publish_event(event)
        await mark_processed("starinfinity", dedup_identifier)
        published += 1

        log.info(
            "starinfinity_overdue_task_event",
            task_id=item_id,
            title=_extract_title(item)[:80],
            due_date=due_date,
        )

    log.debug(
        "starinfinity_poll_completed",
        overdue_tasks_found=len(all_overdue),
        events_published=published,
    )


def _extract_due_date(item: dict) -> datetime | None:
    """Try to extract a due date from item attributes/values."""
    # StarInfinity items have a "values" dict keyed by attribute ID
    values = item.get("values", {})
    if isinstance(values, dict):
        for val in values.values():
            if isinstance(val, dict) and val.get("type") == "date":
                try:
                    return datetime.fromisoformat(val["data"].replace("Z", "+00:00"))
                except (KeyError, ValueError, TypeError):
                    pass
            # Also try raw string dates
            if isinstance(val, str) and "T" in val:
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except ValueError:
                    pass

    # Check top-level due_date field
    for key in ("due_date", "dueDate", "deadline"):
        raw = item.get(key)
        if raw:
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                pass

    return None


def _extract_title(item: dict) -> str:
    """Extract item title/name from the item data."""
    for key in ("name", "title", "label"):
        if item.get(key):
            return str(item[key])
    # Try values
    values = item.get("values", {})
    if isinstance(values, dict):
        for val in values.values():
            if isinstance(val, dict) and val.get("type") == "text":
                return str(val.get("data", ""))[:200]
    return f"Item {item.get('id', '?')}"
