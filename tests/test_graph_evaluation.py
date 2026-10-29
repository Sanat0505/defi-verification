from copy import deepcopy

from evaluation.graph_runner import build_cases, evidence_matches, graph_key, reference, timing


def facts():
    return {
        "preflight": {"deployments": [{"deployment": "aave-v3:11155111", "fresh": True}]},
        "deployments": [{"key": "aave-v3:11155111", "verified": True, "actions": ["supply"],
                         "asset_coverage": "official-address-book-complete"}],
        "contracts": [{"deployment": "aave-v3:11155111", "verified": True, "function_verified": True,
                       "role": "pool", "purpose": "execute", "action": "supply",
                       "address": "pool", "signature": "supply", "selector": "0x617ba037"}],
        "reserves": [{"deployment": "aave-v3:11155111", "symbol": "USDT", "token_chain_id": 11155111,
                      "actions": ["supply"], "link_active": True, "active": True, "verified": True,
                      "token_verified": True, "address": "token", "decimals": 6}],
        "pools": [],
    }


INTENT = {"protocol": "Aave V3", "action": "supply", "token_in": "USDT", "amount": "10"}


def test_reference_dataset_uses_all_draft_core_intents_not_model_successes():
    cases = build_cases()
    assert len(cases) == 136
    assert len([c for c in cases if "expanded_500" in c["source_dataset"]]) == 100
    assert len({graph_key(c["intent"]) for c in cases}) < len(cases)


def test_snapshot_reference_requires_active_verified_action_specific_path():
    snapshot = facts()
    assert reference(INTENT, snapshot)["decision"] == "APPROVED"
    snapshot["reserves"][0]["active"] = False
    assert reference(INTENT, snapshot)["decision"] == "REJECTED"
    snapshot["deployments"][0]["asset_coverage"] = "partial"
    assert reference(INTENT, snapshot)["decision"] == "INSUFFICIENT_EVIDENCE"


def test_snapshot_staleness_is_not_wrong_relationship_rejection():
    snapshot = facts()
    snapshot["preflight"]["deployments"][0]["fresh"] = False
    assert reference(INTENT, snapshot)["decision"] == "INSUFFICIENT_EVIDENCE"
    assert reference({**INTENT, "protocol": "Compound V2"}, snapshot)["decision"] == "UNSUPPORTED"


def test_approval_evidence_checks_selector_and_asset_not_just_status():
    expected = reference(INTENT, facts())
    actual = deepcopy(expected["paths"][0])
    assert evidence_matches(actual, expected, "supply")
    actual["verified_asset"] = "wrong-token"
    assert not evidence_matches(actual, expected, "supply")


def test_r6_timing_uses_every_measured_return_time():
    result = timing([{"wall_latency_ms": x} for x in [1, 1999, 2000, 2001]])
    assert result["requests"] == 4
    assert result["within_2000_ms"] == 3
    assert result["percentage_within_2000_ms"] == 75
