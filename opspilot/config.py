"""Application configuration, loaded from environment variables (prefix ``OP_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OP_", env_file=".env", extra="ignore")

    environment: str = "local"
    # Retrieval score below which the matched runbook is treated as low-confidence
    # and the incident is flagged for human triage. On this runbook library a
    # clearly in-domain incident scores ~0.35 and up, while an out-of-domain one
    # (no runbook really fits) tops out around ~0.26 even when it shares an
    # incidental symptom word, so 0.30 sits in the gap between the two. Two honest
    # caveats: a very tersely described in-domain incident (one matching term) can
    # fall below it and is sent to a human — the safe outcome; and this threshold
    # is NOT the safety mechanism. It only rates the *match*; every system-changing
    # step is gated behind explicit human approval regardless of confidence. It is
    # an operator dial: raise it to send more to a human, lower it to auto-match
    # more.
    min_confidence: float = 0.30
    # LLM provider cascade for the triage summary; extractive fallback otherwise.
    llm_spec: str = "anthropic,openai,gemini,deepseek,ollama"
    llm_max_tokens: int = 200


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
