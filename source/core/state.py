"""Process-local clarification state and one-time execution capabilities.

Approved operations stay on the server; clients receive only a capability ID.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from source.core.config import settings
from source.core.models import ApprovedOperation, IntentCandidate


@dataclass
class PendingIntent:
    intent: IntentCandidate
    missing_fields: list[str]
    expires_at: float


class ConversationStore:
    def __init__(self, ttl_seconds: int = settings.conversation_ttl_seconds):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, PendingIntent] = {}
        self._lock = threading.Lock()

    def get(self, conversation_id: str) -> PendingIntent | None:
        with self._lock:
            item = self._items.get(conversation_id)
            if item and item.expires_at > time.time():
                return item
            self._items.pop(conversation_id, None)
            return None

    def put(self, conversation_id: str, intent: IntentCandidate, missing_fields: list[str]):
        with self._lock:
            self._items[conversation_id] = PendingIntent(
                intent=intent,
                missing_fields=list(missing_fields),
                expires_at=time.time() + self.ttl_seconds,
            )

    def clear(self, conversation_id: str | None):
        if not conversation_id:
            return
        with self._lock:
            self._items.pop(conversation_id, None)


@dataclass
class Capability:
    operation: ApprovedOperation
    expires_at: float
    claimed: bool = False


class VerificationCapabilityStore:
    def __init__(self, ttl_seconds: int = settings.verification_ttl_seconds):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, Capability] = {}
        self._lock = threading.Lock()

    def issue(self, operation: ApprovedOperation) -> str:
        capability_id = secrets.token_urlsafe(32)
        with self._lock:
            self._items[capability_id] = Capability(
                operation=operation.model_copy(deep=True),
                expires_at=time.time() + self.ttl_seconds,
            )
        return capability_id

    def claim(self, capability_id: str) -> ApprovedOperation | None:
        """Atomically claim a live capability; a capability can execute at most once."""
        operation, _status = self.claim_with_status(capability_id)
        return operation

    def claim_with_status(
        self, capability_id: str
    ) -> tuple[ApprovedOperation | None, str]:
        """Claim a capability and retain an auditable failure classification."""
        with self._lock:
            item = self._items.get(capability_id)
            if not item:
                return None, "VERIFICATION_MISSING"
            if item.expires_at <= time.time():
                self._items.pop(capability_id, None)
                return None, "VERIFICATION_EXPIRED"
            if item.claimed:
                self._items.pop(capability_id, None)
                return None, "VERIFICATION_REUSED"
            item.claimed = True
            return item.operation.model_copy(deep=True), "VERIFICATION_CLAIMED"


conversation_store = ConversationStore()
capability_store = VerificationCapabilityStore()
