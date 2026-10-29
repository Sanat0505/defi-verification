import json
import zipfile

import pytest

from knowledge.catalog import permission
from knowledge.model import abi_type, build_graph, parse_abi, signature
from knowledge.sources import SourceBundle, digest


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def test_pinned_interfaces_are_complete_and_overloads_preserved(graph):
    for interface in (n for n in graph.nodes.values() if n["label"] == "Interface"):
        functions = [e for e in graph.edges.values() if e["start"] == interface["key"] and graph.nodes[e["end"]]["label"] == "Function"]
        assert len(functions) == interface["properties"]["function_count"]
    overloads = [n for n in graph.nodes.values() if n["label"] == "Function" and n["properties"]["interface"] == "INonfungiblePositionManager" and n["properties"]["name"] == "safeTransferFrom"]
    assert len(overloads) == 2
    assert len({n["properties"]["selector"] for n in overloads}) == 2


def test_known_selectors_match_execution_boundary(graph):
    implemented = [n["properties"] for n in graph.nodes.values() if n["label"] == "Function" and n["properties"]["prototype_adapter_implemented"]]
    assert {p["selector"] for p in implemented} == {"0x617ba037", "0x69328dec", "0xa415bcad", "0x573ade81", "0x04e45aaf"}
    assert all(p["wallet_eligibility"] == "not_evaluated" for p in implemented)
    assert all(p["interface"] in {"IPool", "SwapRouter02"} for p in implemented)


def test_reserve_infrastructure_and_share_tokens_have_distinct_roles(graph):
    infrastructure = [n for n in graph.nodes.values() if n["properties"].get("role") in {"oracle", "interest_rate_strategy"}]
    assert infrastructure and all(n["label"] == "Contract" for n in infrastructure)
    wrappers = [n for n in graph.nodes.values() if n["properties"].get("role") == "stata_token"]
    assert wrappers and all(n["label"] == "Token" for n in wrappers)
    for wrapper in wrappers:
        assert any(e["start"] == wrapper["key"] and e["type"] == "CANDIDATE_INTERFACE" for e in graph.edges.values())


def test_staking_borrowing_and_transfer_remain_distinct(graph):
    operations = [n["properties"] for n in graph.nodes.values() if n["label"] == "Operation"]
    assert any(p["action"] == "stake" and p["module"] == "aave-umbrella" for p in operations)
    assert not any(p["action"] == "stake" and p["module"] == "aave-v3" for p in operations)
    assert not any(p["action"] == "borrow" and p["module"] == "uniswap-v3" for p in operations)
    assert all(p["prototype_support"] == "knowledge_only" for p in operations if p["action"] in {"stake", "transfer-atokens", "transfer-position"})
    assert "deployment:aave-umbrella:11155111" not in graph.nodes
    assert any(n["properties"].get("code") == "ethereum_sepolia_not_listed" for n in graph.nodes.values())


def test_tuple_arrays_and_nested_parameters():
    parameter = {"type": "tuple[][2]", "components": [{"type": "address"}, {"type": "tuple", "components": [{"type": "uint256"}]}]}
    assert abi_type(parameter) == "(address,(uint256))[][2]"
    assert signature({"name": "f", "inputs": [parameter]}) == "f((address,(uint256))[][2])"
    with pytest.raises(ValueError, match="components"):
        abi_type({"type": "tuple"})


def test_unknown_write_permission_is_not_inferred_public():
    assert permission("IPool", {"name": "futureAdminMethod", "stateMutability": "nonpayable"}) == "unreviewed"
    assert permission("IQuoterV2", {"name": "quoteExactInput", "stateMutability": "nonpayable"}) == "simulation_only"
    assert permission("IPoolConfigurator", {"name": "setSupplyCap", "stateMutability": "nonpayable"}) == "privileged_role_required"


def test_source_bundle_rejects_tampering_and_unlisted_members(tmp_path):
    manifest = tmp_path / "lock.json"
    archive = tmp_path / "sources.zip"
    manifest.write_text(json.dumps({"format_version": 1, "sources": [{"key": "source", "bytes": 4, "sha256": digest(b"good")}] }))
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("source", "evil")
    with pytest.raises(ValueError, match="hash mismatch"):
        SourceBundle(manifest, archive)
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("source", "good")
        z.writestr("extra", "unexpected")
    with pytest.raises(ValueError, match="members differ"):
        SourceBundle(manifest, archive)


def test_typescript_parser_never_executes_expressions():
    with pytest.raises(ValueError):
        parse_abi("export const ABI = require('something');", "typescript_abi")
    with pytest.raises(ValueError):
        parse_abi("// generated\nexport const ABI = [runCode()] as const;", "typescript_abi")


def test_graph_rejects_missing_evidence_or_dangling_edges(graph):
    from knowledge.model import Graph
    sample = Graph()
    sample.node("Function", "unsafe", name="unknown")
    with pytest.raises(ValueError, match="Unsourced"):
        sample.validate()
    sample = Graph()
    sample.node("Module", "module")
    sample.edge("module", "HAS_INTERFACE", "missing")
    with pytest.raises(ValueError, match="Dangling"):
        sample.validate()


def test_rebuild_is_deterministic(graph):
    assert graph.snapshot_id == build_graph().snapshot_id
