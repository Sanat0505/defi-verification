import asyncio

from source.core.models import Decision
from source.llm import intent_parser


def test_parser_accepts_fenced_json_and_validates(monkeypatch):
    monkeypatch.setattr(intent_parser, "_call_model", lambda prompt: {
        "action": "trade", "protocol": "uniswap", "token_in": "weth",
        "token_out": "usdt", "amount": "0.1", "chain": None,
    })
    result = asyncio.run(intent_parser.parse_intent("natural wording"))
    assert result.status == Decision.APPROVED
    assert result.intent.action == "swap"


def test_parser_failure_does_not_leak_exception(monkeypatch):
    def fail(_prompt):
        raise RuntimeError("secret upstream detail")
    monkeypatch.setattr(intent_parser, "_call_model", fail)
    result = asyncio.run(intent_parser.parse_intent("swap something"))
    assert result.status == Decision.ERROR
    assert "secret" not in result.message


def test_json_parser_rejects_extra_text():
    try:
        intent_parser._parse_json_object('Here is JSON: {"action":"swap"}')
    except ValueError:
        pass
    else:
        raise AssertionError("extra text was accepted")
