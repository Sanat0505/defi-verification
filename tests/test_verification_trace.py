from datetime import datetime, timedelta, timezone

import pytest

from core.models import VerificationTrace
from db import verifier
from db.verification_trace import TOKEN_OBSERVATIONS, diagnose_path, knowledge_context


class Rows(list):
    def single(self):
        return self[0] if self else None


class Session:
    def __init__(self, *, complete=True, fail_diagnostics=False, missing_token=False, witnesses=()):
        self.state = dict(key="aave-v3:11155111",source_url="fixture:source",
                          last_successful_sync_at=datetime.now(timezone.utc).isoformat(),
                          asset_coverage="official-address-book-complete" if complete else "partial",
                          pool_discovery_complete=complete,last_sync_status="SUCCESS")
        self.fail_diagnostics=fail_diagnostics
        self.missing_token=missing_token
        self.witnesses=witnesses
        self.queries=[]

    def __enter__(self):return self
    def __exit__(self,*_):return False
    def run(self,query,**params):
        self.queries.append(str(query))
        if str(query)==verifier.KNOWLEDGE_STATE:return Rows([self.state])
        if str(query) in (verifier.CYPHER_SWAP,verifier.CYPHER_LENDING):return Rows()
        if self.fail_diagnostics:raise RuntimeError("sensitive transport details")
        if str(query)==TOKEN_OBSERVATIONS:
            return Rows([dict(symbol=s,candidates=[] if self.missing_token else [dict(address="0x1")])for s in params['symbols']])
        return Rows(self.witnesses)


def test_diagnostic_failure_cannot_change_complete_rejection(monkeypatch):
    session=Session(fail_diagnostics=True)
    monkeypatch.setattr(verifier,"get_session",lambda:session)
    result=verifier.verify_intent("Aave V3","UNKNOWN",action="supply")
    assert result['decision']=='REJECTED'
    assert result['trace']['diagnostic_status']=='unavailable'
    assert result['trace']['failures']==[]
    assert 'sensitive' not in str(result)
    VerificationTrace.model_validate(result['trace'])


def test_unexpected_diagnostic_exception_keeps_disposition(monkeypatch):
    monkeypatch.setattr(verifier,"get_session",lambda:Session())
    monkeypatch.setattr(verifier,"diagnose_path",lambda *_:(_ for _ in ()).throw(ValueError('failure')))
    assert verifier.verify_intent('Aave V3','USDC',action='supply')['decision']=='REJECTED'


@pytest.mark.parametrize('complete,expected',[(True,'REJECTED'),(False,'INSUFFICIENT_EVIDENCE')])
def test_missing_entity_observation_is_scoped_by_coverage(monkeypatch,complete,expected):
    monkeypatch.setattr(verifier,'get_session',lambda:Session(complete=complete,missing_token=True))
    r=verifier.verify_intent('Aave V3','MISSING',action='supply')
    assert r['decision']==expected
    f=r['trace']['failures'][0]
    assert f['rule_id']=='GRAPH.ENTITY.TOKEN_NOT_FOUND'
    assert f['subject']=={'label':'Token','symbol':'MISSING','chain_id':11155111}
    assert f['expected']=={'present':True} and f['observed']['present'] is False
    assert r['knowledge']['complete'] is complete
    assert r['knowledge']['source_url']=='fixture:source'


def test_unresolved_multiple_failure_does_not_invent_an_edge(monkeypatch):
    monkeypatch.setattr(verifier,'get_session',lambda:Session())
    r=verifier.verify_intent('Aave V3','USDC',action='borrow')
    assert r['decision']=='REJECTED'
    assert r['trace']['diagnostic_status']=='not_localized'
    assert r['trace']['failures'][0]['observed']['specific_cause'] is None
    assert 'relationship' not in r['trace']['failures'][0]['subject']


def test_inactive_relationship_records_expected_and_observed_values(monkeypatch):
    witness=dict(relationship='HAS_RESERVE',source={'key':'aave-v3:11155111'},target={'address':'0x1'},
                 expected_properties={'active':True},present=True,observed_properties={'active':False,'role':None})
    monkeypatch.setattr(verifier,'get_session',lambda:Session(witnesses=[witness]))
    r=verifier.verify_intent('Aave V3','USDC',action='supply')
    f=r['trace']['failures'][0]
    assert f['rule_id']=='GRAPH.RELATIONSHIP.HAS_RESERVE'
    assert f['expected']['properties']['active'] is True
    assert f['observed']['present'] is True and f['observed']['properties']['active'] is False


def test_stale_knowledge_stops_before_relationship_diagnostics(monkeypatch):
    s=Session();s.state['last_successful_sync_at']=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
    monkeypatch.setattr(verifier,'get_session',lambda:s)
    r=verifier.verify_intent('Aave V3','USDC',action='supply')
    assert r['decision']=='INSUFFICIENT_EVIDENCE' and r['rule_id']=='KNOWLEDGE.STALE'
    assert len(s.queries)==1
    assert r['trace']['failures'][0]['observed']['age_hours']>r['knowledge']['max_age_hours']


def test_scope_failure_never_queries_graph(monkeypatch):
    monkeypatch.setattr(verifier,'get_session',lambda:(_ for _ in ()).throw(AssertionError()))
    r=verifier.verify_intent('Curve','USDC','WETH')
    assert r['decision']=='UNSUPPORTED' and r['rule_id']=='SCOPE.PROTOCOL'
    assert r['trace']['failures'][0]['evidence_scope']=='configured_scope'


def test_failure_model_rejects_undocumented_fields():
    with pytest.raises(ValueError):
        VerificationTrace(rule_id='x',diagnostic_status='observed',knowledge={},invented=True)
