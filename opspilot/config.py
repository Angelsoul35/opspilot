"""Application configuration, loaded from environment variables (prefix ``OP_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OP_", env_file=".env", extra="ignore")

    environment: str = "local"
    # Retrieval score below which the matched runbook is low-confidence and the
    # incident is flagged for human triage.
    min_confidence: float = 0.08
    # LLM provider cascade for the triage summary; extractive fallback otherwise.
    llm_spec: str = "anthropic,openai,gemini,deepseek,ollama"
    llm_max_tokens: int = 200


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
