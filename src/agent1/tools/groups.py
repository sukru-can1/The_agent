"""Contextual tool filtering — send only relevant tools per event source."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import EventSource
from agent1.common.settings import get_settings

log = get_logger(__name__)

# Tool group definitions — each group maps to a list of tool names.
TOOL_GROUPS: dict[str, list[str]] = {
    "gmail": [
        "gmail_get_new_emails",
        "gmail_get_email",
        "gmail_draft_reply",
        "gmail_send_approved",
        "gmail_label_email",
    ],
    "gchat_agent": [
        "gchat_post_message",
        "gchat_reply_as_agent",
        "gchat_get_messages",
    ],
    "gchat_user": [
        "gchat_reply_as_user",
        "gchat_list_my_spaces",
    ],
    "google_drive": [
        "drive_search",
        "drive_read_document",
    ],
    "freshdesk": [
        "freshdesk_get_tickets",
        "freshdesk_get_ticket",
        "freshdesk_add_note",
        "freshdesk_update_ticket",
    ],
    "starinfinity": [
        "starinfinity_list_boards",
        "starinfinity_get_tasks",
        "starinfinity_create_task",
        "starinfinity_update_task",
    ],
    "feedbacks": [
        "feedbacks_get_insights",
        "feedbacks_get_overview",
        "feedbacks_get_trustpilot_reviews",
        "feedbacks_get_tasks",
        "feedbacks_get_survey_responses",
        "feedbacks_start_auto_reporter",
        "feedbacks_trigger_trustpilot_sync",
    ],
    "memory": [
        "memory_search",
        "memory_store_incident",
        "memory_store_knowledge",
    ],
    "admin": [
        "create_dynamic_tool",
        "list_dynamic_tools",
    ],
}

# Which settings attributes must be non-empty for a group to be available.
CREDENTIAL_REQUIREMENTS: dict[str, list[str]] = {
    "gmail": ["google_refresh_token"],
    "gchat_agent": ["google_service_account_json"],
    "gchat_user": ["google_refresh_token"],
    "google_drive": ["google_refresh_token"],
    "freshdesk": ["freshdesk_api_key"],
    "starinfinity": ["starinfinity_api_key"],
    "feedbacks": ["feedbacks_api_key"],
}

# Source → additional groups (beyond the always-included ones).
SOURCE_GROUPS: dict[str, list[str]] = {
    "gmail": ["gmail", "google_drive", "freshdesk", "starinfinity"],
    "gchat": ["gmail", "google_drive", "freshdesk", "starinfinity", "feedbacks", "gchat_user"],
    "freshdesk": ["freshdesk", "starinfinity", "gmail"],
    "starinfinity": ["starinfinity", "freshdesk"],
    "feedbacks": ["feedbacks", "gchat_user"],
    "scheduler": ["gmail", "freshdesk", "feedbacks", "starinfinity"],
    "dashboard": list(TOOL_GROUPS.keys()),  # ALL groups
    "admin": list(TOOL_GROUPS.keys()),  # ALL groups
}

# Always included regardless of source.
ALWAYS_INCLUDED = ["memory", "gchat_agent"]


def get_available_groups() -> set[str]:
    """Return groups whose credentials are present. Groups without requirements always pass."""
    settings = get_settings()
    available: set[str] = set()
    for group in TOOL_GROUPS:
        reqs = CREDENTIAL_REQUIREMENTS.get(group)
        if not reqs:
            available.add(group)
            continue
        if all(getattr(settings, attr, "") for attr in reqs):
            available.add(group)
    return available


def get_tool_names_for_source(source: EventSource) -> set[str]:
    """Return the set of tool names that should be sent to the LLM for a given source."""
    available = get_available_groups()
    groups = set(ALWAYS_INCLUDED)
    groups.update(SOURCE_GROUPS.get(source.value, []))

    # Intersect with credential-available groups
    active_groups = groups & available

    names: set[str] = set()
    for g in active_groups:
        names.update(TOOL_GROUPS.get(g, []))

    log.info(
        "tools_selected",
        source=source.value,
        tool_count=len(names),
        groups=sorted(active_groups),
    )
    return names
