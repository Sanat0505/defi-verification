"""Check saved evidence without model calls, graph access, or report writes."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

from evaluation.source_import import CACHE, FILES, SOURCE_SHA256


ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "evaluation"


def check_manifest(manifest: Path, root: Path = ROOT, *, base: Path | None = None) -> list[str]:
    base = manifest.parent if base is None else base
    failures = []
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line)
        if not match:
            failures.append(f"{manifest}:{line_number}: invalid checksum entry")
            continue
        expected, name = match.groups()
        path = (base / name).resolve()
        if not path.is_relative_to(root.resolve()):
            failures.append(f"{manifest}: path outside repository: {name}")
        elif not path.is_file():
            failures.append(f"{manifest}: missing {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected.lower():
            failures.append(f"{manifest}: checksum mismatch for {name}")
    return failures


def main() -> int:
    files = [path for path in EVALUATION.rglob("*")
             if path.is_file() and "local-runs" not in path.relative_to(EVALUATION).parts]
    manifests = sorted(path for path in files if path.suffix == ".sha256")
    archives = sorted(path for path in files if path.suffix == ".zip")
    failures = []
    for manifest in manifests:
        failures.extend(check_manifest(manifest))
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as stream:
                bad_member = stream.testzip()
                if bad_member:
                    failures.append(f"{archive}: corrupt member {bad_member}")
        except (OSError, zipfile.BadZipFile) as exc:
            failures.append(f"{archive}: {type(exc).__name__}")
    snapshot_members = 0
    for manifest in sorted(path for path in files if path.name.endswith("source_snapshot_manifest.json")):
        records = json.loads(manifest.read_bytes())
        if isinstance(records, dict):
            records = records.get("files", records)
        if isinstance(records, dict):
            records = [{"path": name, "sha256": digest} for name, digest in records.items()]
        try:
            with zipfile.ZipFile(manifest.with_name(manifest.name.replace("_manifest.json", ".zip"))) as stream:
                for record in records:
                    name = record["path"].replace("\\", "/")
                    if hashlib.sha256(stream.read(name)).hexdigest() != record["sha256"]:
                        failures.append(f"{manifest}: snapshot checksum mismatch for {name}")
                    snapshot_members += 1
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            failures.append(f"{manifest}: {type(exc).__name__}")
    for name, relative in FILES.items():
        path = CACHE / Path(relative).name
        if not path.is_file():
            failures.append(f"Missing pinned source: {path}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]:
            failures.append(f"Pinned source checksum mismatch: {path}")
    print(json.dumps({
        "manifests_checked": len(manifests),
        "archives_checked": len(archives),
        "snapshot_members_checked": snapshot_members,
        "pinned_sources_checked": len(FILES),
        "passed": not failures,
        "failures": failures,
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
