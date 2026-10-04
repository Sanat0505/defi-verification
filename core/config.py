"""Environment-backed configuration with safe, centralized defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    supported_chain_id: int = _int_env("SUPPORTED_CHAIN_ID", 11155111)
    supported_network: str = os.getenv("SUPPORTED_NETWORK", "Ethereum Sepolia")
    knowledge_max_age_hours: int = _int_env("KNOWLEDGE_MAX_AGE_HOURS", 168)
    verification_ttl_seconds: int = _int_env("VERIFICATION_TTL_SECONDS", 600)
    conversation_ttl_seconds: int = _int_env("CONVERSATION_TTL_SECONDS", 1800)
    api_timeout_seconds: int = _int_env("API_TIMEOUT_SECONDS", 45)


settings = Settings()
