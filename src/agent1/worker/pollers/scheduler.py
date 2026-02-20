"""Cron-like scheduler for periodic tasks (morning brief, polling, etc.)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def _run_gmail_poller() -> None:
    """Poll Gmail for new emails."""
    from agent1.worker.pollers.gmail_poller import poll_gmail

    await poll_gmail()


async def _run_freshdesk_poller() -> None:
    """Poll Freshdesk for new/updated tickets."""
    from agent1.worker.pollers.freshdesk_poller import poll_freshdesk

    await poll_freshdesk()


async def _run_feedbacks_poller() -> None:
    """Poll feedbacks DB for new complaints."""
    from agent1.worker.pollers.feedbacks_poller import poll_feedbacks

    await poll_feedbacks()


async def _run_starinfinity_poller() -> None:
    """Poll StarInfinity for overdue tasks."""
    from agent1.worker.pollers.starinfinity_poller import poll_starinfinity

    await poll_starinfinity()


async def _run_gchat_poller() -> None:
    """Poll Google Chat spaces for messages to Sukru (user mode)."""
    from agent1.worker.pollers.gchat_poller import poll_gchat

    await poll_gchat()


async def _run_pattern_detection() -> None:
    """Run pattern detection checks."""
    from agent1.worker.pattern_detector import detect_patterns

    await detect_patterns()


async def _run_feedback_analysis() -> None:
    """Run feedback pattern analysis (edit learning)."""
    from agent1.feedback.analyzer import analyze_edit_patterns

    patterns = await analyze_edit_patterns(min_edits=3)
    if patterns:
        from agent1.common.db import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            for p in patterns:
                # Store as knowledge if not already stored
                existing = await conn.fetchval(
                    """
                    SELECT id FROM knowledge
                    WHERE category = 'edit_pattern'
                      AND source = $1
                      AND active = true
                    """,
                    f"feedback:{p['sender_domain']}",
                )
                if not existing:
                    await conn.execute(
                        """
                        INSERT INTO knowledge (category, content, source, active)
                        VALUES ('edit_pattern', $1, $2, true)
                        """,
                        f"Drafts for {p['sender_domain']} ({p['category']}) are edited {p['avg_edit_ratio']*100:.0f}% on average. Adjust tone/style accordingly.",
                        f"feedback:{p['sender_domain']}",
                    )
        log.info("feedback_patterns_stored", count=len(patterns))


async def _morning_brief() -> None:
    """Publish morning briefing event at 06:00 UTC."""
    event = Event(
        source=EventSource.SCHEDULER,
        event_type="morning_brief",
        priority=Priority.LOW,
        payload={"date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        idempotency_key=f"morning_brief:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
    )
    await publish_event(event)
    log.info("morning_brief_scheduled")


async def _daily_summary() -> None:
    """Publish daily summary event at 18:00 UTC."""
    event = Event(
        source=EventSource.SCHEDULER,
        event_type="daily_summary",
        priority=Priority.LOW,
        payload={"date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        idempotency_key=f"daily_summary:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
    )
    await publish_event(event)
    log.info("daily_summary_scheduled")


async def _run_baseline_update() -> None:
    """Update adaptive baselines from historical data. Run weekly."""
    from agent1.intelligence.analytics_engine import update_baselines
    await update_baselines()


async def _run_load_baselines() -> None:
    """Load baselines from DB on startup."""
    try:
        from agent1.intelligence.analytics_engine import load_baselines
        await load_baselines()
    except Exception:
        pass  # Table may not exist yet


async def run_scheduler() -> None:
    """Main scheduler loop — runs pollers and cron tasks."""
    settings = get_settings()
    interval = settings.heartbeat_interval_seconds

    log.info("scheduler_started", interval=interval)

    # Load baselines on startup
    await _run_load_baselines()

    poll_count = 0
    while True:
        try:
            poll_count += 1
            now = datetime.now(timezone.utc)

            log.info("scheduler_tick", poll=poll_count, time=now.isoformat())

            # Run pollers concurrently
            await asyncio.gather(
                _run_gmail_poller(),
                _run_freshdesk_poller(),
                _run_feedbacks_poller(),
                _run_starinfinity_poller(),
                _run_gchat_poller(),
                _run_pattern_detection(),
                return_exceptions=True,
            )

            # Run feedback analysis less frequently (every 10th tick)
            if poll_count % 10 == 0:
                try:
                    await _run_feedback_analysis()
                except Exception:
                    log.exception("feedback_analysis_error")

            # Cron-like checks (approximate — within one polling interval)
            if now.hour == 6 and now.minute < (interval // 60 + 1):
                await _morning_brief()
            elif now.hour == 18 and now.minute < (interval // 60 + 1):
                await _daily_summary()

            # Weekly baseline update (Sunday midnight)
            if now.weekday() == 6 and now.hour == 0 and now.minute < (interval // 60 + 1):
                try:
                    await _run_baseline_update()
                except Exception:
                    log.exception("baseline_update_error")

        except Exception:
            log.exception("scheduler_error")

        await asyncio.sleep(interval)
