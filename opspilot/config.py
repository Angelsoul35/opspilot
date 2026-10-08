"""Application configuration, loaded from environment variables (prefix ``OP_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OP_", env_file=".env", extra="ignore")

    environment: str = "local"
    # Retrieval score below which the matched runbook is low-confidence and the
    # incident is flagged for human triage. Set so that a genuinely out-of-domain
    # incident (no runbook really fits) is flagged rather than silently matched to
    # the nearest book: in practice in-domain incidents score ~0.35+ and
    # out-of-domain ones ~0.2 or less, so the gap sits around here. It is an
    # operator dial — raise it to send more to a human, lower it to auto-match
    # more — and it never bypasses the action gate: system-changing steps always
    # need approval regardless.
    min_confidence: float = 0.25
    # LLM provider cascade for the triage summary; extractive fallback otherwise.
    llm_spec: str = "anthropic,openai,gemini,deepseek,ollama"
    llm_max_tokens: int = 200


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
