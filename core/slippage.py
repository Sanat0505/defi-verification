"""Exact slippage conversion shared by interpretation and execution policy."""

from decimal import Decimal, InvalidOperation, localcontext
import re


def parse_slippage(value) -> int | None:
    """Accept a model-extracted value/unit pair; never round or widen a bound."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"value", "unit"}:
        raise ValueError("Specify slippage as a number with percent or bps units.")
    number, unit = value["value"], value["unit"]
    if not isinstance(number, str) or len(number) > 100 or not re.fullmatch(r"\d+(?:\.\d+)?", number.strip()):
        raise ValueError("Slippage must be an explicit positive decimal string.")
    if unit not in {"percent", "bps"}:
        raise ValueError("Slippage units must be percent or bps.")
    try:
        with localcontext() as context:
            context.prec = max(32, len(number) + 4)
            bps = Decimal(number.strip()) * (100 if unit == "percent" else 1)
    except InvalidOperation as exc:
        raise ValueError("Invalid slippage value.") from exc
    if bps != bps.to_integral_value():
        raise ValueError("Slippage must resolve to a whole basis point; no rounding is applied.")
    if not 1 <= bps <= 500:
        raise ValueError("Slippage must be between 1 and 500 basis points (0.01% to 5%).")
    return int(bps)
