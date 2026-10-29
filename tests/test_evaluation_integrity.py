import hashlib

from evaluation.check_integrity import check_manifest


def test_integrity_check_detects_changed_and_missing_evidence_without_writing(tmp_path):
    evidence = tmp_path / "results.json"
    original = b'{"decision": "REJECTED"}\n'
    evidence.write_bytes(original)
    manifest = tmp_path / "MANIFEST.sha256"
    manifest.write_text(f"{hashlib.sha256(original).hexdigest()}  results.json\n")
    assert check_manifest(manifest, tmp_path) == []

    evidence.write_bytes(b'{"decision": "APPROVED"}\n')
    assert "checksum mismatch" in check_manifest(manifest, tmp_path)[0]
    assert evidence.read_bytes() == b'{"decision": "APPROVED"}\n'
    evidence.unlink()
    assert "missing results.json" in check_manifest(manifest, tmp_path)[0]


def test_integrity_check_resolves_evaluation_relative_manifest(tmp_path):
    evaluation = tmp_path / "evaluation"
    package = evaluation / "paired"
    package.mkdir(parents=True)
    payload = b"saved observation"
    (package / "case.json").write_bytes(payload)
    manifest = package / "MANIFEST.sha256"
    manifest.write_text(f"{hashlib.sha256(payload).hexdigest()}  paired/case.json\n")
    assert check_manifest(manifest, tmp_path, base=evaluation) == []


def test_integrity_check_rejects_malformed_entries(tmp_path):
    manifest = tmp_path / "MANIFEST.sha256"
    manifest.write_text("not a checksum\n")
    assert "invalid checksum entry" in check_manifest(manifest, tmp_path)[0]
