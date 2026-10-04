"""Authoritative structured models for interpretation, verification, and execution."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class Decision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    UNSUPPORTED = "UNSUPPORTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ERROR = "ERROR"


class IntentCandidate(BaseModel):
    """A partial or complete semantic intent; never contains blockchain addresses."""

    model_config = ConfigDict(extra="forbid")

    action: str | None = None
    protocol: str | None = None
    token_in: str | None = None
    token_out: str | None = None
    amount: Decimal | None = None
    chain: str | None = None
    chain_id: int | None = None

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value, "f")


class IntentResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Decision
    intent: IntentCandidate | None = None
    message: str
    missing_fields: list[str] = Field(default_factory=list)
    error_code: str | None = None


class PromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prompt: str = Field(min_length=1, max_length=2000)
    wallet_address: str | None = None
    conversation_id: str | None = Field(default=None, max_length=128)
    new_operation: bool = False


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    verification_id: str = Field(min_length=20, max_length=200)
    wallet_address: str = Field(min_length=42, max_length=42)


class ApprovedOperation(BaseModel):
    """Server-side execution capability payload derived only from graph verification."""

    model_config = ConfigDict(extra="forbid")

    intent: IntentCandidate
    decision: Decision = Decision.APPROVED
    protocol: str
    action: str
    chain_id: int
    network: str
    verified_address: str
    verified_function: str
    verified_selector: str
    routes: list[dict[str, Any]] = Field(default_factory=list)
    verified_pool: str | None = None
    verified_asset: str | None = None
    verified_asset_symbol: str | None = None
    verified_asset_decimals: int | None = None
    interest_rate_mode: int | None = None
    referral_code: int = 0
