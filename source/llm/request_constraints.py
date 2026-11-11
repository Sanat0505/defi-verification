"""Conservative text checks supplement, but do not replace, semantic extraction.

These rules catch explicit known conditions even if the model omits them. They
are deliberately not a claim to recognize every possible natural-language
constraint. Unrecognized slippage wording is blocked rather than defaulted.
"""

import re

from source.core.slippage import parse_slippage


UNSUPPORTED_PATTERNS = {
    "deadline": r"\bdeadline\b|\bwithin\s+(?:\d+(?:\.\d+)?|an?|one|two|five|ten|sixty)\s+(?:seconds?|minutes?|hours?|days?)\b|\b(?:before|by)\s+(?:\d|today\b|tomorrow\b|noon\b|midnight\b)",
    "custom_recipient_or_beneficiary": r"\b0x[a-fA-F0-9]{40}\b|\bon behalf\b|\brecipient\b|\bsend\s+(?:the\s+)?(?:output|proceeds)\b",
    "gas_or_fee_condition": r"\b(?:gas|fees?)\b",
    "minimum_output": r"\b(?:minimum|min)[ -]?(?:out(?:put)?|receive)\b|\b(?:receive|get)\s+(?:at least|no less than|a minimum)\b|\b(?:at least|no less than)\s+\d",
    "fiat_denominated_amount": r"[$€£]|\bworth\b|\b\d+(?:\.\d+)?\s+(?:USD(?!\s+Coin\b)|EUR|GBP)\b",
    "relative_or_whole_position_amount": r"\b(?:half|quarter)\s+(?:of\s+)?(?:my|the)\b|\ball\s+(?:of\s+)?(?:my|the|available|USDT|USDC|WETH|ETH|DAI|tokens)\b|\b(?:entire|full)\s+(?:\w+\s+){0,3}(?:balance|position|debt)\b|\d+\s*%\s+of\b",
    "fixed_interest_rate": r"\b(?:fixed|stable)\s+(?:interest\s+)?rate\b",
    "position_condition": r"\bhealth factor\b|\bcollateral(?:ization)?\s+ratio\b",
    "price_impact_condition": r"\bprice impact\b",
    "conditional_execution": r"\bonly if\b|\bprovided that\b|\bunless\b",
    "multiple_operations": r"\b(?:then|and|afterwards|followed by)\s+(?:please\s+)?(?:swap|exchange|trade|supply|deposit|withdraw|borrow|repay|bridge|stake|transfer)\b",
    "exact_output_or_input_budget": r"\b(?:exact[ -]?output|maximum input)\b|\b(?:receive|get|buy)\s+exactly\s+\d|\bspend\s+(?:at most|no more than|up to)\b",
}

NUMBER = r"[+-]?\d+(?:\.\d+)?"
UNIT = r"(?:%|percent\b|bps\b|basis points?\b)"
AFTER = re.compile(
    rf"\bslippage(?:\s+(?:tolerance|limit|cap))?\s*(?:(?:of|is|at|to|at most|no more than|up to|<=)\s*)?(?P<value>{NUMBER})\s*(?P<unit>{UNIT})",
    re.I,
)
BEFORE = re.compile(rf"(?P<value>{NUMBER})\s*(?P<unit>{UNIT})\s+(?:(?:maximum|max)\s+)?slippage\b", re.I)


def constraint_labels(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("unhandled_constraints must be a list of at most 20 strings")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 250 for item in value):
        raise ValueError("Invalid unhandled constraint description")
    return list(dict.fromkeys(item.strip() for item in value))


def enforce_request_constraints(prompt: str, raw: dict) -> dict:
    result = dict(raw)
    flags = constraint_labels(result.get("unhandled_constraints"))
    flags.extend(name for name, pattern in UNSUPPORTED_PATTERNS.items() if re.search(pattern, prompt, re.I))
    mentions = list(re.finditer(r"\bslippage\b", prompt, re.I))
    matches = list(AFTER.finditer(prompt)) + list(BEFORE.finditer(prompt))
    if mentions:
        # Every slippage mention must belong to a recognized inclusive bound.
        if any(not any(m.start() <= mention.start() < m.end() for m in matches) for mention in mentions):
            flags.append("unrecognized_slippage_condition")
        elif re.search(r"(?:\bless than\b|\bbelow\b|\bunder\b|<(?![=]))[^;\n]{0,40}\bslippage\b", prompt, re.I):
            flags.append("strict_slippage_bound")
        else:
            try:
                stated = {
                    parse_slippage({"value": m["value"], "unit": "percent" if m["unit"].lower() in {"%", "percent"} else "bps"})
                    for m in matches
                }
            except ValueError:
                # Let normalization return a specific invalid-slippage rejection
                # using the literal user value, even if the model changed it.
                if len(matches) == 1:
                    match = matches[0]
                    result["slippage"] = {"value": match["value"], "unit": "percent" if match["unit"].lower() in {"%", "percent"} else "bps"}
                else:
                    flags.append("invalid_or_conflicting_slippage")
            else:
                try:
                    extracted = parse_slippage(result.get("slippage"))
                except ValueError:
                    flags.append("invalid_slippage_extraction")
                else:
                    if len(stated) != 1:
                        flags.append("conflicting_slippage_conditions")
                    elif extracted is None or extracted not in stated:
                        flags.append("slippage_not_preserved")
    elif result.get("slippage") is not None:
        flags.append("unverified_slippage_expression")
    result["unhandled_constraints"] = list(dict.fromkeys(flags))[:20]
    return result
