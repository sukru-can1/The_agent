"""Tests for analytics engine — correlation, baselines, reports."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent1.intelligence.analytics_engine import (
    update_baselines,
    is_anomaly,
    update_threshold,
)


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


def test_is_anomaly_no_baseline_uses_fallback():
    """Without a baseline, use the fixed threshold of 3."""
    assert is_anomaly("freshdesk", "ticket_updated", 5, baseline=None) is True
    assert is_anomaly("freshdesk", "ticket_updated", 2, baseline=None) is False


def test_is_anomaly_with_baseline():
    """With a baseline, anomaly is mean + 2*stddev."""
    baseline = {"mean": 8.0, "stddev": 2.0}
    # Threshold = 8 + 2*2 = 12
    assert is_anomaly("freshdesk", "ticket_updated", 13, baseline=baseline) is True
    assert is_anomaly("freshdesk", "ticket_updated", 11, baseline=baseline) is False


def test_is_anomaly_minimum_threshold():
    """Even with baseline, minimum threshold is 2."""
    baseline = {"mean": 0.1, "stddev": 0.05}
    # Threshold would be 0.2, but minimum is 2
    assert is_anomaly("freshdesk", "ticket_updated", 3, baseline=baseline) is True
    assert is_anomaly("freshdesk", "ticket_updated", 1, baseline=baseline) is False


@pytest.mark.asyncio
async def test_update_baselines_queries_4_weeks(mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [
        {"source": "freshdesk", "event_type": "ticket_updated",
         "dow": 1, "hod": 9, "mean_count": 8.2, "stddev_count": 2.1},
    ]

    with patch("agent1.intelligence.analytics_engine.get_pool", new_callable=AsyncMock, return_value=pool):
        await update_baselines()

    conn.fetch.assert_called_once()
    # Should have called execute for the upsert
    conn.execute.assert_called()


@pytest.mark.asyncio
async def test_update_threshold(mock_pool):
    pool, conn = mock_pool
    conn.execute.return_value = "UPDATE 1"

    config = {
        "source": "freshdesk",
        "event_type": "ticket_updated",
        "day_of_week": 1,
        "hour_of_day": 9,
        "mean_count": 10.0,
        "stddev_count": 3.0,
    }

    with patch("agent1.intelligence.analytics_engine.get_pool", new_callable=AsyncMock, return_value=pool):
        await update_threshold(config)

    conn.execute.assert_called_once()
