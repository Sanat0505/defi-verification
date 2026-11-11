import sys

from evaluation.traceability_runner import ROOT, load_before
from source.core.models import Decision
from source.db.connection import get_session


def test_frozen_verifier_loads_without_modifying_evidence_or_leaking_imports():
    snapshot = ROOT / "evaluation/sources/graph_before_verifier.py"
    original = snapshot.read_bytes()
    names = ("core", "core.config", "core.models", "db", "db.connection")
    previous = {name: sys.modules.get(name) for name in names}

    verifier = load_before()

    assert verifier.Decision is Decision
    assert verifier.get_session is get_session
    assert snapshot.read_bytes() == original
    assert {name: sys.modules.get(name) for name in names} == previous
