"""Application settings from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration loaded from environment variables."""

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    # --- Anthropic ---
    anthropic_api_key: str = ""
    claude_model_default: str = "claude-sonnet-4-5-20250929"
    claude_model_haiku: str = "claude-haiku-4-5-20251001"
    claude_model_opus: str = "claude-opus-4-0-20250514"

    # --- Voyage AI ---
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3"
    embedding_dim: int = 1024

    # --- Database ---
    database_url: str = "postgresql://agent1:agent1@localhost:5432/agent1"
    db_pool_min: int = 2
    db_pool_max: int = 10

    # --- Feedbacks DB (read-only) ---
    feedbacks_database_url: str = ""

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Google Auth ---
    google_service_account_json: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # --- Gmail ---
    gmail_user_email: str = "sukru.can@glamira-group.com"

    # --- Google Chat Spaces ---
    gchat_space_alerts: str = ""
    gchat_space_log: str = ""
    gchat_space_summary: str = ""
    gchat_dm_sukru: str = ""
    gchat_poll_spaces: list[str] = Field(default_factory=list)  # space IDs to poll in user mode
    gchat_user_email: str = "sukru.can@glamira-group.com"  # to filter out own messages

    # --- Freshdesk ---
    freshdesk_domain: str = "glmr.freshdesk.com"
    freshdesk_api_key: str = ""

    # --- StarInfinity ---
    starinfinity_base_url: str = ""
    starinfinity_api_key: str = ""

    # --- LangFuse ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- MCP ---
    mcp_config_path: str = "mcp_servers.json"
    dynamic_tools_enabled: bool = True

    # --- Agent ---
    agent_name: str = "The Agent1"
    heartbeat_interval_seconds: int = 300
    log_level: str = "INFO"
    environment: str = "development"

    # --- Webhook server ---
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    # --- Webhook security ---
    google_project_number: str = ""  # Google Cloud project number for Chat JWT verification
    freshdesk_webhook_secret: str = ""  # Shared secret for Freshdesk webhooks

    # --- Queue ---
    queue_max_retries: int = 3
    dedup_ttl_seconds: int = 3600
    lock_ttl_seconds: int = 30

    # --- Rate limits ---
    rate_limit_emails_per_hour: int = 10
    rate_limit_chat_messages_per_minute: int = 30

    # --- Guardrails ---
    restricted_contacts: list[str] = Field(default_factory=list)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
