import os

import pytest

from knowledge.database import _publish, database_name, summary
from knowledge.model import Graph
from knowledge.observations import ReadOnlyRpc, add_observations, observe_chain


@pytest.mark.parametrize("name", ["neo4j", "system", "thesis-eval-20261019", "origin", "defi-knowledge-unsafe`", "defi-knowledge-a;DROP DATABASE neo4j"])
def test_database_guard_rejects_protected_or_injected_names(name):
    with pytest.raises(ValueError):
        database_name(name)


def test_database_guard_accepts_separate_database():
    assert database_name("defi-knowledge-expanded") == "defi-knowledge-expanded"


def test_rpc_cannot_submit_transactions():
    with pytest.raises(ValueError, match="read-only"):
        ReadOnlyRpc("https://unused.invalid").call("eth_sendRawTransaction", ["0x"])


def test_wrong_rpc_network_is_rejected_before_import():
    class WrongChain:
        def call(self, method, params):
            assert method == "eth_chainId"
            return "0x1"
    with pytest.raises(ValueError, match="chain mismatch"):
        observe_chain(Graph(), 11155111, WrongChain())


def test_reorg_during_observations_prevents_publication():
    class Reorg:
        def call(self, method, params):
            if method == "eth_chainId":
                return hex(11155111)
            assert method == "eth_getBlockByNumber"
            return {"number": "0x42", "timestamp": "0x1234", "hash": "0x" + ("a" if params[0] == "latest" else "b") * 64}
    graph = Graph()
    graph.node("Chain", "chain:11155111", chain_id=11155111)
    with pytest.raises(ValueError, match="Block changed"):
        observe_chain(graph, 11155111, Reorg())


def test_absent_rpc_creates_gap_and_never_claims_negative_deployment(monkeypatch):
    monkeypatch.delenv("MAINNET_RPC", raising=False)
    monkeypatch.delenv("SEPOLIA_RPC", raising=False)
    graph = add_observations(Graph(), enabled=True)
    assert len(graph.nodes) == 2
    assert all(n["properties"]["implies_unsupported"] is False for n in graph.nodes.values())


@pytest.mark.skipif(os.getenv("KNOWLEDGE_INTEGRATION") != "1", reason="Explicit opt-in to the local expanded knowledge database")
def test_live_publication_is_idempotent_and_rollback_keeps_active_snapshot():
    from db.connection import get_driver
    before = summary()
    graph = Graph()
    graph.node("Module", "rollback-probe", name="Transaction rollback test")
    snapshot_id = graph.snapshot_id
    driver = get_driver()
    class RollbackProbe(Exception):
        pass

    with driver.session(database=database_name()) as session:
        def transaction(tx):
            first = _publish(tx, graph, snapshot_id)
            assert first["already_present"] is False
            second = _publish(tx, graph, snapshot_id)
            assert second["already_present"] is True
            assert tx.run("MATCH (s:KnowledgeSnapshot {key:$id})-[:CONTAINS]->(n) RETURN count(n) AS n", id=snapshot_id).single()["n"] == 1
            raise RollbackProbe()
        with pytest.raises(RollbackProbe):
            session.execute_write(transaction)
        assert session.run("MATCH (s:KnowledgeSnapshot {key:$id}) RETURN count(s) AS n", id=snapshot_id).single()["n"] == 0
    assert summary()["snapshot_id"] == before["snapshot_id"]


