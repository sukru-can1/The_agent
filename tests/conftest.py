"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set environment variables for testing."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://agent1:agent1@localhost:5432/agent1_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    # Reset settings singleton
    import agent1.common.settings as s
    s._settings = None
    yield
    s._settings = None
