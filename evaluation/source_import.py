"""Download pinned public evaluation inputs and audit them without using an LLM.

Raw files stay in the ignored .cache directory. No model, wallet or database is
called. Upstream labels concern intent/transaction alignment, not our task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "37bd0f345efb166e3cebc6839e75481e57ce3c90"
REPOSITORY = "https://github.com/duanyiyao/intent-tx-18k"
CACHE = ROOT / ".cache" / "intent-tx-18k" / COMMIT
FILES = {
    "uniswap": "dataset/eg_uniswap_samples.json",
    "compound": "dataset/compound_samples_20251112_085506.json",
    "cow": "dataset/cow_samples_20251110_171339.json",
    "license": "LICENSE",
}
SOURCE_SHA256 = {
    "uniswap": "6930c416aabc24e2316ec3fdc0cbfcb6b70dfe54effccc673f474b79a1b74e30",
    "compound": "e3d8d7d95dc867bb94c7cd8a978e2828f497063ca88e6f91479fc6495a7396cd",
    "cow": "d2613a92b1eddfe4b1b9b6af28e99b9ac3bfa96cca1873e2798ebfbba84a8423",
    "license": "1142c0ef577ea422fef58058b5ef386d34ca72b491f17465798c96486401462b",
}


def fetch(name: str, cache: Path = CACHE) -> dict:
    relative = FILES[name]
    url = f"https://raw.githubusercontent.com/duanyiyao/intent-tx-18k/{COMMIT}/{relative}"
    destination = cache / Path(relative).name
    if not destination.exists():
        request = Request(url, headers={"User-Agent": "defi-thesis-evaluation/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = response.read(50_000_001)
        if len(payload) > 50_000_000:
            raise ValueError("Source exceeds the 50 MB download limit")
        if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError(f"Downloaded source checksum mismatch: {name}")
        if name != "license":
            records = json.loads(payload)
            if not isinstance(records, list):
                raise ValueError("Expected a JSON array of source records")
        cache.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    payload = destination.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256[name]:
        raise ValueError(f"Cached source checksum mismatch: {name}")
    return {
        "name": name,
        "repository": REPOSITORY,
        "commit": COMMIT,
        "path": relative,
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "local_path": str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination),
    }


def load_source(name: str, cache: Path = CACHE) -> list[dict]:
    payload = (cache / Path(FILES[name]).name).read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256[name]:
        raise ValueError(f"Cached source checksum mismatch: {name}")
    return json.loads(payload)


def source_family(record: dict) -> str:
    # Transaction variants share a historical transaction even if wording changes.
    tx_hash = (record.get("metadata") or {}).get("tx_hash")
    if tx_hash:
        return str(tx_hash).lower()
    return hashlib.sha256(record["human_intent"].strip().encode()).hexdigest()


def constraint_flags(text: str) -> list[str]:
    patterns = {
        "slippage": r"slippage|price impact|\bbps\b|basis points",
        "minimum_output": r"minimum|min(?:imum)?[ -]?(?:out|receive)|at least|no less than",
        "deadline": r"deadline|\bwithin\b|\bminutes?\b|\bhours?\b|\bseconds?\b|\bby \d|before|expire|\btoday\b",
        "recipient": r"recipient|\b0x[a-fA-F0-9]{40}\b|send (?:the )?(?:output|proceeds)|to my wallet",
        "fee_limit": r"\bgas\b|\bfees?\b|costs?",
        "fiat_denominated_amount": r"\$|\bworth\b|\bUSD\b",
        "exact_output_or_budget": r"exact(?:ly)? (?:out|receive)|spend (?:at most|no more)|maximum input|up to|at most|no more than",
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, text, re.I)]


def audit(records: list[dict]) -> dict:
    protocols, chains, labels, flags = Counter(), Counter(), Counter(), Counter()
    for record in records:
        tx = record.get("proposed_tx") or {}
        protocols[str(tx.get("protocol"))] += 1
        chains[str(tx.get("chain_id"))] += 1
        labels[str(record.get("label"))] += 1
        flags.update(constraint_flags(record.get("human_intent", "")))
    return {
        "records": len(records),
        "unique_intent_texts": len({r.get("human_intent", "") for r in records}),
        "explicit_v3_intent_texts": sum(bool(re.search(r"\bv3\b", r.get("human_intent", ""), re.I)) for r in records),
        "unique_source_families": len({source_family(r) for r in records}),
        "proposed_transaction_protocols_not_query_labels": dict(protocols),
        "proposed_transaction_chain_ids_not_query_labels": dict(chains),
        "upstream_labels_not_reference_outcomes": dict(labels),
        "heuristic_text_flags_nonexclusive_not_gold_labels": dict(flags),
        "note": "Text flags are a screening aid, not exhaustive semantic annotation. Transaction metadata must not fill unstated query fields.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=tuple(FILES), action="append", required=True)
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation" / "sources" / "intent_tx_18k_manifest.json")
    args = parser.parse_args(argv)
    sources = []
    for name in args.source:
        item = fetch(name)
        if name != "license":
            item["audit"] = audit(load_source(name))
        sources.append(item)
        print(json.dumps(item, indent=2), flush=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
