"""Offline checks for the evaluation harness's safety and fixture structure."""
import json
from pathlib import Path
import pytest
from evaluation import controlled_graph as runner


def test_live_database_name_is_refused_before_driver_access(monkeypatch):
    monkeypatch.setattr(runner,'DB','neo4j')
    monkeypatch.setattr(runner,'get_driver',lambda:(_ for _ in ()).throw(RuntimeError('must not access driver')))
    with pytest.raises(AssertionError):
        runner.ensure_fixture_database()


def test_all_twelve_fixture_definitions_have_one_required_path(monkeypatch):
    snapshot=json.loads(next((Path(__file__).resolve().parents[1]/'evaluation/graph').glob('snapshot-20261019*.json')).read_bytes())
    specs=runner.fixture_specs(snapshot)
    assert len(specs)==12
    monkeypatch.setattr(runner,'clear_fixture',lambda:None)
    monkeypatch.setattr(runner,'query',lambda *a,**k:[])
    for spec in specs:
        f=runner.materialize(spec)
        keys=[n['key'] for n in f['nodes']]
        assert len(keys)==len(set(keys))
        assert all(n['props']['_eval_owner']==runner.OWNER for n in f['nodes'])
        assert sum(n['label']=='ProtocolDeployment' for n in f['nodes'])==1
        assert sum(n['label'] in ['Pool','Reserve'] for n in f['nodes'])==1
        assert sum(e['type']=='EXPOSES_FUNCTION' and e['a']=='contract' for e in f['edges'])==1
        assert sum(e['type']=='IMPLEMENTS_ACTION' and e['a']=='function' for e in f['edges'])==1
        assert all(e['a'] in keys and e['b'] in keys for e in f['edges'])
