from pathlib import Path


def test_non_executable_approval_is_not_rendered_as_an_error():
    javascript = Path("static/app.js").read_text(encoding="utf-8")
    assert 'data.executable ? "Ready to execute on Sepolia testnet"' in javascript
    assert 'class="info-msg"' in javascript
    assert "Relationship verification succeeded, but blockchain execution" not in javascript


def test_slippage_display_uses_verified_execution_parameters():
    javascript = Path("static/app.js").read_text(encoding="utf-8")
    assert "data.execution_parameters" in javascript
    assert "Maximum slippage" in javascript
    assert "configured default" in javascript
    assert "your limit" in javascript
