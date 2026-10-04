from datetime import datetime, timedelta, timezone

from db import verifier


class Result:
    def __init__(self, rows):
        self.rows = rows
    def single(self):
        return self.rows[0] if self.rows else None
    def __iter__(self):
        return iter(self.rows)


class Session:
    def __init__(self, state, relationship_rows=None):
        self.state = state
        self.relationship_rows = relationship_rows or []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def run(self, query, **params):
        if "last_successful_sync_at" in query:
            return Result([self.state] if self.state else [])
        return Result(self.relationship_rows)


def fresh_state(**changes):
    value = {
        "last_successful_sync_at": datetime.now(timezone.utc).isoformat(),
        "last_synced_at": None,
        "pool_discovery_complete": True,
        "asset_coverage": "official-address-book-complete",
        "source_url": "official",
    }
    value.update(changes)
    return value


def test_complete_graph_miss_is_rejected(monkeypatch):
    monkeypatch.setattr(verifier, "get_session", lambda: Session(fresh_state()))
    result = verifier.verify_intent("Uniswap V3", "AAVE", "USDT", "swap")
    assert result["decision"] == "REJECTED"


def test_incomplete_graph_miss_is_insufficient_evidence(monkeypatch):
    monkeypatch.setattr(verifier, "get_session", lambda: Session(fresh_state(pool_discovery_complete=False)))
    result = verifier.verify_intent("Uniswap V3", "AAVE", "USDT", "swap")
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"


def test_stale_graph_cannot_approve(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    monkeypatch.setattr(verifier, "get_session", lambda: Session(fresh_state(last_successful_sync_at=old)))
    result = verifier.verify_intent("Aave V3", "USDT", action="supply")
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"
    assert "stale" in result["reason"].lower()


def test_neo4j_failure_is_controlled(monkeypatch):
    def fail():
        raise RuntimeError("connection unavailable")
    monkeypatch.setattr(verifier, "get_session", fail)
    result = verifier.verify_intent("Aave V3", "USDT", action="supply")
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"


def test_unknown_protocol_is_unsupported_without_graph(monkeypatch):
    monkeypatch.setattr(verifier, "get_session", lambda: (_ for _ in ()).throw(AssertionError()))
    result = verifier.verify_intent("Curve", "USDT", "WETH", "swap")
    assert result["decision"] == "UNSUPPORTED"
