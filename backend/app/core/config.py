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
    AI_PROVIDER: str = "tfidf"  # 'tfidf', 'groq', 'gemini', 'llm', 'codebert', 'mock'
    AI_MODEL: str = "tfidf-word-v1"
    AI_MODEL_NAME: Optional[str] = None
    AI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    AI_API_BASE_URL: Optional[str] = None
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_OUTPUT_TOKENS: int = 2048
    AI_FALLBACK_ENABLED: bool = True
    AI_CACHE_ENABLED: bool = True
    AI_MAX_INPUT_CHARS: int = 16000

    def get_effective_model_name(self) -> str:
        """Returns configured AI_MODEL_NAME if specified, otherwise provider default."""
        if self.AI_MODEL_NAME and self.AI_MODEL_NAME.strip():
            return self.AI_MODEL_NAME.strip()
        provider = (self.AI_PROVIDER or "").strip().lower()
        if provider in ("groq", "groqcloud"):
            return "qwen/qwen3.8-27b"
        elif provider in ("gemini", "google"):
            return "gemini-3.8-flash"
        return (self.AI_MODEL or "tfidf-word-v1").strip()

    def get_gemini_api_key(self) -> Optional[str]:
        """Resolves Gemini API key with priority: GEMINI_API_KEY -> AI_API_KEY -> env."""
        key = self.GEMINI_API_KEY or self.AI_API_KEY
        if not key:
            import os
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY")
        return key.strip() if key else None

    def get_groq_api_key(self) -> Optional[str]:
        """Resolves Groq API key with priority: GROQ_API_KEY -> AI_API_KEY -> env."""
        key = self.GROQ_API_KEY or self.AI_API_KEY
        if not key:
            import os
            key = os.environ.get("GROQ_API_KEY") or os.environ.get("AI_API_KEY")
        return key.strip() if key else None


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
