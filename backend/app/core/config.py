"""Application settings, loaded from environment variables (and a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "PolicyPilot API"
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Databases
    database_url: str = "postgresql+asyncpg://policypilot:policypilot@localhost:5432/policypilot"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db_name: str = "policypilot"
    db_check_timeout_seconds: float = 2.0

    # LLM providers (keys are optional so the app and tests run without them)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_chat_model: str = ""
    anthropic_chat_model: str = ""
    gemini_chat_model: str = ""
    default_llm_provider: str = "fake"
    llm_max_output_tokens: int = 1024
    llm_timeout_seconds: float = 60.0
    # Sent only to providers/models that accept it; leave unset for reasoning models.
    chat_temperature: float | None = None

    # Retrieval and chat
    retrieval_top_k: int = 6
    retrieval_min_score: float = 0.2
    chat_history_turns: int = 4
    citation_snippet_chars: int = 240

    # Contract review agent
    max_agent_steps: int = 25
    agent_timeout_seconds: float = 300.0
    agent_max_clauses: int = 30

    # Embeddings
    embedding_provider: str = "openai"
    embedding_model: str = ""
    embedding_dim: int = 1536
    embedding_batch_size: int = 64

    # Ingestion
    max_upload_mb: float = 20.0
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 80
    tokenizer_encoding: str = "cl100k_base"

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
