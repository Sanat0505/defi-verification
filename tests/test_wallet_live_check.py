from evaluation import wallet_live_check as runner


def test_blocked_policy_cannot_reach_preparation_or_whitelist_writes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected wallet mutation/preparation")
    monkeypatch.setattr(runner, "verify_intent", lambda *args: {
        "decision": "APPROVED", "verified_address": "pool", "verified_asset": "token"})
    monkeypatch.setattr(runner.erc4337, "check_session", lambda *args: {
        "success": True, "allowed": False, "reason_code": "POLICY_EXPIRED"})
    for name in ["prepare_aave", "execute_aave", "execute_swap", "add_to_whitelist"]:
        monkeypatch.setattr(runner.erc4337, name, forbidden)
    result = runner.run_case("supply", "Aave V3", "USDT", None, "10")
    assert result["status"] == "BLOCKED_BY_CURRENT_POLICY"
    assert not result["prepare_called"]
    assert len(result["current_destination_checks"]) == 2
    assert not result["transaction_broadcast"]


def test_graph_block_skips_wallet_entirely(monkeypatch):
    monkeypatch.setattr(runner, "verify_intent", lambda *args: {"decision": "INSUFFICIENT_EVIDENCE"})
    monkeypatch.setattr(runner.erc4337, "check_session", lambda *args: (_ for _ in ()).throw(AssertionError("wallet called")))
    result = runner.run_case("withdraw", "Aave V3", "USDT", None, "10")
    assert result["status"] == "NOT_REACHED_GRAPH_NOT_APPROVED"


def test_read_only_report_redacts_upstream_urls_and_secret_shaped_hex():
    result = runner.redact({"reason": "RPC https://example.test/private-token failed", "key": "0x" + "a" * 64})
    assert "private-token" not in result["reason"]
    assert "a" * 64 not in result["key"]
