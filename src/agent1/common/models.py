"""Pydantic domain models shared across the application."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Priority ---

class Priority(IntEnum):
    """Event priority levels. Lower number = higher priority."""

    CRITICAL = 1
    HIGH = 3
    MEDIUM = 5
    LOW = 7
    BACKGROUND = 9


# --- Event status ---

class EventStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


# --- Event source ---

class EventSource(StrEnum):
    GMAIL = "gmail"
    GCHAT = "gchat"
    FRESHDESK = "freshdesk"
    STARINFINITY = "starinfinity"
    FEEDBACKS = "feedbacks"
    SCHEDULER = "scheduler"
    ADMIN = "admin"


# --- Classification ---

class EmailClassification(StrEnum):
    URGENT = "urgent"
    NEEDS_RESPONSE = "needs_response"
    FYI = "fyi"
    SPAM = "spam"


class Complexity(StrEnum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


# --- Core models ---

class Event(BaseModel):
    """An event in the processing queue."""

    id: UUID = Field(default_factory=uuid4)
    source: EventSource
    event_type: str
    priority: Priority = Priority.MEDIUM
    payload: dict = Field(default_factory=dict)
    idempotency_key: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: EventStatus = EventStatus.PENDING
    retry_count: int = 0
    error: str | None = None


class ClassificationResult(BaseModel):
    """Output of the Haiku fast classifier."""

    category: str
    urgency: Priority
    complexity: Complexity
    involves_vip: bool = False
    involves_financial: bool = False
    needs_response: bool = False
    confidence: float = 0.0
    detected_language: str = "en"
    is_teachable_rule: bool = False


class EmailDraft(BaseModel):
    """An email draft pending approval."""

    id: int | None = None
    gmail_message_id: str
    gmail_thread_id: str = ""
    from_address: str = ""
    to_address: str = ""
    subject: str = ""
    original_body: str = ""
    draft_body: str = ""
    edited_body: str | None = None
    status: str = "pending"
    classification: EmailClassification = EmailClassification.NEEDS_RESPONSE
    context_used: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ActionLog(BaseModel):
    """Record of an agent action for audit trail."""

    system: str
    action_type: str
    details: dict = Field(default_factory=dict)
    outcome: str = "success"
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class MemorySearchResult(BaseModel):
    """A result from memory search."""

    id: int
    category: str
    content: str
    source: str = ""
    similarity: float = 0.0
    table: str = ""  # "incidents" or "knowledge"
