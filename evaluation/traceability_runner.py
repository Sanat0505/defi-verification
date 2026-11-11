"""Paired before/after graph regressions; no LLM or production graph writes.

Use historical fixture specifications and references unchanged. Writes are confined
to the explicitly owned thesis-eval-20261024 database. Persist every completed call
to an append-only journal before proceeding. Never overwrite a completed run.
"""
import importlib.util
import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.cache/evaluation-runs/traceability'
sys.path.insert(0,str(ROOT))
from source.core.config import settings
from source.db import sync,verifier
from source.db.connection import close_driver,get_driver
from evaluation.graph_runner import reference,evidence_matches,build_cases
from evaluation.graph_stage import snapshot
from evaluation import controlled_graph as harness

CACHED_CALLS={}


def load(path):return json.loads(path.read_bytes())
def save(name,value):
    temp=OUT/(name+'.tmp')
    temp.write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')
    for attempt in range(20):
        try:
            temp.replace(OUT/name)
            break
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05)
def journal(record):
    with (OUT/'calls.jsonl').open('a',encoding='utf-8')as stream:
        stream.write(json.dumps(record,default=str)+'\n');stream.flush()


def load_before():
    spec=importlib.util.spec_from_file_location('verifier_before_traceability',ROOT/'evaluation/sources/graph_before_verifier.py')
    mod=importlib.util.module_from_spec(spec)
    # The frozen verifier retains its original imports. Resolve them only while
    # loading it, using the same models and connection as the current runner.
    legacy_imports = {
        name: importlib.import_module(f"source.{name}")
        for name in ("core", "core.config", "core.models", "db", "db.connection")
    }
    with patch.dict(sys.modules, legacy_imports):
        spec.loader.exec_module(mod)
    return mod


def call(module,inputs,phase,case_id,variant,fixture=False,unavailable=False):
    cached=CACHED_CALLS.get((phase,case_id,variant))
    if cached is not None:return dict(cached)
    def fail():raise ConnectionError('Controlled fixture-only graph unavailability')
    getter=fail if unavailable else (lambda:get_driver().session(database=harness.DB)) if fixture else module.get_session
    start=time.perf_counter()
    with patch.object(module,'get_session',getter):actual=module.verify_intent(**inputs)
    r=dict(phase=phase,id=case_id,variant=variant,actual=actual,wall_latency_ms=round((time.perf_counter()-start)*1000,3))
    journal(r);return r


def paired(modules,inputs,phase,case_id,index,**kwargs):
    order=['before','after']if index%2==0 else['after','before']
    out={'order':order}
    for key in order:out[key]=call(modules[key],inputs,phase,case_id,key,**kwargs)
    return out


def identity_matches(identity,node):
    if node['label'] not in identity.get('labels',[]):return False
    props=node['props']
    keys=[k for k in ('key','address','symbol','name','signature','selector','chain_id')if props.get(k)is not None]
    return bool(keys)and all(identity.get(k)==props[k]for k in keys)


def audit(actual,expected,fixture,mutation_detail,inputs):
    nodes={n['key']:n for n in fixture['nodes']}
    c1=actual.get('decision')==expected
    c2=bool(actual.get('rule_id')or actual.get('error_code')or actual.get('reason_code'))
    checks={};matches=[];wrong=[]
    if not mutation_detail:
        wanted=dict(verified_address=nodes['contract']['props']['address'],
                    verified_function=nodes['function']['props']['signature'],verified_selector=nodes['function']['props']['selector'],
                    protocol=inputs['protocol'],action=inputs['action'],chain_id=11155111)
        if inputs['action']=='swap':
            wanted['verified_pool']=nodes['resource']['props']['address']
            route=(actual.get('routes')or[{}])[0]
            for k,v in dict(token_in_address=nodes['token_in']['props']['address'],token_out_address=nodes['token_out']['props']['address'],
                            pool_fee=nodes['resource']['props']['fee'],quoter_address=nodes['quoter']['props']['address']).items():checks[k]=route.get(k)==v
        else:
            wanted.update(verified_asset=nodes['token_in']['props']['address'],verified_asset_decimals=nodes['token_in']['props']['decimals'])
        checks.update({k:actual.get(k)==v for k,v in wanted.items()});c3=all(checks.values());c4=None
    else:
        detail=mutation_detail
        required=next(e['props']for e in fixture['edges']if(e['a'],e['type'],e['b'])==(detail['from'],detail['relationship'],detail['to']))
        for f in (actual.get('trace')or{}).get('failures',[]):
            s=f['subject']
            correct=s.get('relationship')==detail['relationship']and identity_matches(s.get('source',{}),nodes[detail['from']])and identity_matches(s.get('target',{}),nodes[detail['to']])
            (matches if correct else wrong).append(f)
        c3=bool(matches)and not wrong
        c4=bool(matches)and all(f['expected']=={'present':True,'properties':required}and f['observed']=={'present':False,'properties':{}}for f in matches)and not wrong
    return dict(C1_explicit_decision=c1,C2_stable_rule_or_reason_identifier=c2,
                C3_correct_specific_entity_or_broken_link=c3,C4_expected_and_observed_mismatch_values=c4,
                all_applicable=c1 and c2 and c3 and c4 is not False,
                matching_witnesses=len(matches),unexpected_witnesses=len(wrong),approval_checks=checks)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    existing=load(OUT/'regression_results.json')if (OUT/'regression_results.json').exists()else None
    if existing and (not args.resume or existing['metadata'].get('completed')):
        raise RuntimeError('Use --resume only for an incomplete run; never overwrite completed results.')
    if not existing and (OUT/'calls.jsonl').exists():raise RuntimeError('Unmatched journal requires explicit recovery.')
    if existing:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        (OUT/f'checkpoint_before_resume_{stamp}.json').write_bytes((OUT/'regression_results.json').read_bytes())
        for line in (OUT/'calls.jsonl').read_text().splitlines():
            row=json.loads(line);key=(row['phase'],row['id'],row['variant'])
            assert key not in CACHED_CALLS
            CACHED_CALLS[key]=row
    logging.disable(logging.CRITICAL)
    harness.DB='thesis-eval-20261024';harness.OWNER='traceability-regression-20261024-v1'
    old=load_before();modules={'before':old,'after':verifier}
    previous=load(ROOT/'evaluation/graph/original_controlled_references.json')
    specs=previous['fixtures']
    assert len(specs)==12
    if not existing:
        save('controlled_references.json',dict(previous,post_change_database=harness.DB,
             note='Historical fixture semantics and labels reused; timestamps regenerated as fresh controlled state, not live acquisition.'))
    before=harness.live_fingerprint()
    if existing:
        assert before==existing['metadata']['live_before'], 'Live graph changed across interruption'
        facts=load(OUT/'live_snapshot_before.json')
    else:
        facts=snapshot();save('live_snapshot_before.json',facts)
    original=load(ROOT/'evaluation/600_prompts/results.json')['reference_graph_results']
    graph_plan=[dict(id=r['id'],input={k:r['intent'].get(k) for k in ('protocol','token_in','token_out','action','chain_id')},
                     graph_key=r['graph_key'],expected=reference(r['intent'],facts),historical_expected=r['draft_expected'])for r in original]
    if existing:assert graph_plan==load(OUT/'independent_graph_references.json')
    else:save('independent_graph_references.json',graph_plan)
    results=dict(metadata=dict(started_at_utc=datetime.now(timezone.utc).isoformat(),live_before=before,fixture_database=harness.DB,
                              model_calls=0,production_graph_writes=False,paired_order='Alternating before/after order; no warmups excluded.',
                              query_plan_note='Diagnostic queries were EXPLAIN-validated during development; no cold-cache claim.',
                              expected_review='Historical assistant-drafted references; no new human-review claim.'),D=[],E=[],graph=[],boundaries=[])
    code_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in ('source/db/verifier.py','source/db/verification_trace.py','source/core/models.py')}
    if existing:
        results=existing
        if results['metadata'].get('code_hashes'):assert results['metadata']['code_hashes']==code_hashes
        results['metadata'].setdefault('continuations',[]).append(dict(resumed_at_utc=datetime.now(timezone.utc).isoformat(),
            retained_calls=len(CACHED_CALLS),retained_graph_cases=len(results['graph']),reason='Windows checkpoint replacement file lock; calls preserved without rerun'))
    results['metadata']['code_hashes']=code_hashes
    save('regression_results.json',results)
    harness.ensure_fixture_database()
    try:
        # Independent live graph latency phase precedes fixture runs.
        for index,item in enumerate(graph_plan):
            if any(r['id']==item['id']for r in results['graph']):continue
            pair=paired(modules,item['input'],'independent_graph',item['id'],index)
            for key in ('before','after'):
                pair[key]['decision_match']=pair[key]['actual']['decision']==item['expected']['decision']
                pair[key]['evidence_match']=evidence_matches(pair[key]['actual'],item['expected'],item['input']['action'])
            results['graph'].append(dict(item,**pair));save('regression_results.json',results)
            if(index+1)%40==0:print(f"Independent graph: {index+1}/{len(graph_plan)} pairs",flush=True)
        for index,c in enumerate(c for c in build_cases()if c['category']=='structured_graph_boundary_control'):
            if any(r['id']==c['id']for r in results['boundaries']):continue
            inputs={k:c['intent'].get(k)for k in ('protocol','token_in','token_out','action','chain_id')}
            expected=reference(c['intent'],facts)
            results['boundaries'].append(dict(id=c['id'],expected=expected,input=inputs,**paired(modules,inputs,'boundary',c['id'],index)))
            save('regression_results.json',results)
        for spec in specs:
            for mutation in ['control',*harness.MUTATIONS]:
                if any(r['id']==f"{spec['id']}:{mutation}"for r in results['D']):continue
                fixture=harness.materialize(spec);initial=harness.state()
                changed=harness.delete_edge(spec,mutation)if mutation!='control'else None
                modified=harness.state()
                assert initial['nodes']==modified['nodes']
                expected=previous['D_expected'][mutation];inputs=harness.arguments(spec)
                pair=paired(modules,inputs,'D',f"{spec['id']}:{mutation}",len(results['D']),fixture=True)
                for key in ('before','after'):pair[key]['audit']=audit(pair[key]['actual'],expected,fixture,changed,inputs)
                results['D'].append(dict(id=f"{spec['id']}:{mutation}",fixture_id=spec['id'],mutation=mutation,expected=expected,input=inputs,
                     fixture_definition=fixture,mutation_detail=changed,entities_preserved=True,**pair))
                save('regression_results.json',results);harness.clear_fixture()
            print(f"Controlled relationships: {len(results['D'])}/72 pairs",flush=True)
        for spec in [specs[0],next(s for s in specs if s['action']=='supply')]:
            for condition,expected in previous['E_expected'].items():
                for repeat in range(1,4):
                    ident=f"{spec['protocol_key']}:{condition}:{repeat}"
                    if any(r['id']==ident for r in results['E']):continue
                    harness.materialize(spec);sync_result=None
                    if condition=='stale':
                        stamp=(datetime.now(timezone.utc)-timedelta(hours=settings.knowledge_max_age_hours+1)).isoformat()
                        harness.query('MATCH (d:ProtocolDeployment) SET d.last_successful_sync_at=$stamp',stamp=stamp)
                    elif condition=='incomplete_missing_path':
                        harness.query("MATCH (d:ProtocolDeployment) SET d.pool_discovery_complete=false,d.asset_coverage='partial'")
                        harness.delete_edge(spec,'resource_asset')
                    elif condition=='deactivated_membership':
                        harness.query('MATCH (:ProtocolDeployment)-[r:HAS_POOL|HAS_RESERVE]->() SET r.active=false')
                    elif condition=='failed_refresh_fresh_snapshot_retained':
                        def fail_acquire():raise TimeoutError('Controlled acquisition failure')
                        task=sync.SyncTask('fixture-source',f"{spec['protocol_key']}:11155111",'fixture:controlled-acquisition',fail_acquire,lambda _:None,
                                          lambda _:(_ for _ in ()).throw(AssertionError('No admission expected')))
                        with patch.object(sync,'get_session',lambda:get_driver().session(database=harness.DB)):sync_result=asdict(sync.run_task(task))
                        harness.query("MATCH(s:KnowledgeSource {key:'fixture-source',url:'fixture:controlled-acquisition'}) SET s._eval_owner=$owner,s._eval_id='source'",owner=harness.OWNER)
                    results['E'].append(dict(id=ident,condition=condition,repeat=repeat,expected=expected,sync_result=sync_result,
                        knowledge_state=harness.query('MATCH(d:ProtocolDeployment) RETURN properties(d) AS properties'),
                        **paired(modules,harness.arguments(spec),'E',ident,len(results['E']),fixture=True,unavailable=condition=='database_unavailable')))
                    save('regression_results.json',results);harness.clear_fixture()
            print(f"Knowledge lifecycle: {len(results['E'])}/36 pairs",flush=True)
    finally:
        harness.clear_fixture()
        results['metadata']['fixture_nodes_after_cleanup']=harness.query('MATCH(n) RETURN count(n) AS count')[0]['count']
        results['metadata']['live_after']=harness.live_fingerprint()
        results['metadata']['live_unchanged']=before==results['metadata']['live_after']
        results['metadata']['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        results['metadata']['completed']=len(results['D'])==72 and len(results['E'])==36 and len(results['graph'])==340
        save('regression_results.json',results);close_driver()
    print(json.dumps(dict(counts={k:len(results[k])for k in ('D','E','graph','boundaries')},metadata=results['metadata']),indent=2))


if __name__=='__main__':main()
