from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or .env file."""

    PROJECT_NAME: str = "ChangeGuard"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # GitHub Configuration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_TIMEOUT_SECONDS: int = 30

    # Model configuration
    AI_PROVIDER: str = "tfidf"
    AI_MODEL: str = "tfidf-word-v1"
    AI_API_KEY: Optional[str] = None

    # Monitoring & Worker configuration (Milestone 8)
    MONITORING_ENABLED_BY_DEFAULT: bool = False
    MONITORING_POLL_INTERVAL_SECONDS: int = 60
    MONITORING_STATE_FILE: str = "data/monitoring_state.json"
    MONITORED_REPOSITORIES: str = ""  # Comma-separated list e.g. "octocat/Hello-World,pallets/flask"
    MAX_PROCESSING_RETRIES: int = 3

    # Reporting configuration (Milestone 9)
    ENABLE_GITHUB_REPORTING: bool = False  # Disabled by default; read-only operations

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
