"""Offline checks for the new evaluation adapter, with no provider/database use."""
import json

from evaluation import exploratory_400_runner as runner


def test_reference_call_uses_semantic_parameter_names(monkeypatch):
    seen={}
    def verify(**kwargs):
        seen.update(kwargs)
        return {'decision':'REJECTED'}
    monkeypatch.setattr(runner,'verify_intent',verify)
    result=runner.graph_call({'protocol':'Uniswap V3','action':'swap','token_in':'USDC','token_out':'WETH','chain_id':11155111})
    assert seen=={'protocol':'Uniswap V3','action':'swap','token_in':'USDC','token_out':'WETH','chain_id':11155111}
    assert result['actual']['decision']=='REJECTED'
    assert not result['operational_failure']


def test_draft_selection_and_primary_denominators():
    cases=runner.flatten(json.loads(runner.DEFAULT_DATASET.read_bytes()))
    assert len(cases)==400
    assert all(c['primary'] for c in cases[:200])
    assert not any(c['primary'] for c in cases[200:])
    assert sum(c['graph_eligible'] for c in cases)==220


def test_schema_and_semantic_amount_checks():
    raw={k:None for k in runner.RAW_KEYS};raw['unhandled_constraints']=[]
    assert runner.raw_shape(raw)
    raw['slippage']={'value':'0.5','unit':'percent'}
    assert runner.raw_shape(raw)
    raw['amount']=1.25
    assert not runner.raw_shape(raw)
    assert runner.field_checks({'amount':'1.0'},{'amount':'1'})['amount']['matches']
    assert not runner.field_checks({}, {'slippage_bps':100})['slippage_bps']['matches']


def test_saved_interpretation_is_recoverable_without_model(tmp_path):
    path=tmp_path/'interpretations.jsonl'
    row={'id':'case','resolution':{'status':'ERROR','message':'provider unavailable'}}
    runner.journal(path,row)
    assert runner.saved_interpretations(path)=={'case':row}
