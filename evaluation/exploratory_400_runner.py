"""One exploratory pass over the unreviewed 400-prompt proposal.

Calls the unchanged parser once per prompt, reuses its resolution in the unchanged
pipeline, and independently checks eligible reference intents. No wallet imports,
graph mutations, policy updates or transaction submission. This consumes the
draft as exploratory data; it does not create a reviewed held-out benchmark.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.config import settings
from core.models import IntentCandidate, IntentResolution, PromptRequest
from db.connection import close_driver
from db.verifier import verify_intent
from evaluation.graph_runner import evidence_matches, graph_key, reference, timing
from evaluation.graph_stage import snapshot
from evaluation.run_support import (
    RAW_KEYS as RAW_KEYS,
    Observer,
    digest,
    field_checks,
    journal,
    raw_shape,
    save,
    saved_interpretations,
    stable_snapshot,
    utc,
)
from llm import intent_parser
from services import pipeline

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DATASET=ROOT/'evaluation/400_prompts/dataset_snapshot.json'


def flatten(dataset):
    cases=[]
    for scenario in dataset['scenarios']:
        for prompt in scenario['prompts']:
            cases.append({**{k:v for k,v in scenario.items() if k!='prompts'},**prompt})
    assert len(dataset['scenarios'])==200 and len(cases)==400
    assert len({r['id'] for r in cases})==400
    assert sum(r['primary'] for r in cases)==200
    # Primary formulations first; alternate formulations second, fixed before calls.
    return sorted(cases,key=lambda r:(not r['primary'],r['id']))


def graph_call(intent):
    start=time.perf_counter();exception=None
    try:actual=verify_intent(protocol=intent['protocol'],token_in=intent.get('token_in'),
        token_out=intent.get('token_out'),action=intent['action'],chain_id=intent.get('chain_id',11155111))
    except Exception as exc:
        exception=type(exc).__name__;actual={'decision':'ERROR','error_type':exception}
    return {'actual':actual,'wall_latency_ms':round((time.perf_counter()-start)*1000,3),
            'operational_failure':bool(exception) or actual.get('reason')=='Authoritative graph knowledge is temporarily unavailable.'}


def summary(report):
    records=report['results'];graph=report['reference_graph_results']
    def group(rows):
        return {'prompts':len(rows),'validation_status_matches':sum(r['A']['status_match'] for r in rows),
            'validation_errors':sum(r['A']['actual']['status']=='ERROR' for r in rows),
            'pipeline_status_matches':sum(r['C']['status_match'] for r in rows),
            'joint_reference_matches':sum(r['C']['joint_reference_match'] for r in rows),
            'draft_pipeline_improper_approvals':sum(r['C']['improper_approval'] for r in rows),
            'graph_calls':sum(len(r['C']['graph_calls']) for r in rows),
            'json_objects':sum(r['A']['raw_json_object'] for r in rows),
            'prompt_schema_conformant':sum(r['A']['raw_prompt_schema_conformant'] for r in rows)}
    unique={}
    for r in graph:unique.setdefault(tuple(r['graph_key']),r)
    return {'all_prompts':group(records),'primary_formulations':group([r for r in records if r['primary']]),
        'by_category':{c:group([r for r in records if r['category']==c]) for c in sorted({r['category'] for r in records})},
        'reference_graph':{'completed':len(graph),'distinct_inputs':len(unique),
            'draft_decision_matches':sum(r['decision_match'] for r in graph),
            'snapshot_evidence_matches':sum(r['evidence_match'] for r in graph),
            'operational_failures':sum(r['operational_failure'] for r in graph),
            'timing_all':timing(graph) if graph else None,
            'timing_first_distinct':timing(list(unique.values())) if unique else None},
        'independence_warning':'400 prompts form 200 declared families; family independence is unverified. Alternatives are not independent samples.',
        'joint_reference_match_definition':'Validation and final dispositions match; specified normalized fields and missing fields match for APPROVED/NEEDS_CLARIFICATION references. For other dispositions, this is disposition conformance only, not exhaustive semantic correctness.'}


async def run(args):
    payload=args.dataset.read_bytes();dataset=json.loads(payload);cases=flatten(dataset)
    if not args.allow_unreviewed:
        raise ValueError('This runner is exploratory only; use --allow-unreviewed to explicitly acknowledge draft references.')
    if settings.supported_chain_id!=11155111:raise ValueError('Expected Sepolia configuration')
    if not os.getenv('GROQ_API_KEY'):raise ValueError('GROQ_API_KEY not configured')
    code={str(p.relative_to(ROOT)):digest(p.read_bytes()) for base in ['core','llm','services','db'] for p in (ROOT/base).rglob('*.py')}
    code[str(Path(__file__).relative_to(ROOT))]=digest(Path(__file__).read_bytes())
    code['evaluation/run_support.py']=digest((ROOT/'evaluation/run_support.py').read_bytes())
    protected={name:digest((ROOT/name).read_bytes()) for name in ['.env','wallet/session-whitelist.json'] if (ROOT/name).exists()}
    out=args.resume or args.output_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=bool(args.resume))
    path=out/'results.json'
    if args.resume:
        report=json.loads(path.read_bytes())
        assert report['metadata']['dataset_sha256']==digest(payload)
        assert report['metadata']['code_sha256']==code,'Code changed; do not combine different implementations'
        report['metadata'].setdefault('resumed_at_utc',[]).append(utc())
    else:
        report={'metadata':{'started_at_utc':utc(),'mode':'EXPLORATORY_UNREVIEWED_400_ONE_PASS',
            'final_held_out_evaluation':False,'reference_review':dataset['review_status'],'dataset_frozen_by_researcher':False,
            'dataset_sha256':digest(payload),'dataset_path':str(args.dataset.relative_to(ROOT)),
            'logical_model_calls_planned':400,'passes':1,'family_count':200,'model':settings.llm_model,
            'temperature':0,'reasoning_effort':'low','max_completion_tokens':512,'delay_seconds':args.delay,
            'transport_timeout_seconds':45,'sdk_internal_retries':'Groq SDK default; not individually observed',
            'call_order':'All primary A formulations by ID, then alternate B formulations by ID',
            'code_sha256':code,'protected_sha256':protected,'python':platform.python_version(),
            'graph_mutations':False,'wallet_calls':0,'transactions_broadcast':0,'completion_status':'preflight',
            'cache_state':'No OS/Neo4j cache flush; read-only snapshot audit before timed graph calls; all first and slow calls retained'},
            'reference_graph_results':[],'results':[]}
        (out/'dataset_snapshot.json').write_bytes(payload)
    save(path,report)
    print(f'Output directory: {out}',flush=True)
    facts=snapshot();save(out/('snapshot-resume.json' if args.resume else 'snapshot-before.json'),facts)
    if args.resume:
        before=json.loads((out/'snapshot-before.json').read_bytes())
        assert stable_snapshot(before)==stable_snapshot(facts),'Graph snapshot changed; do not mix runs'
    if not facts['preflight']['freshness_prerequisite_met'] or not facts['invariants']['valid']:
        report['metadata']['completion_status']='blocked_graph_preflight';save(path,report)
        raise RuntimeError('Freshness/invariant prerequisite failed; no model calls started')
    refs=[]
    for case in cases:
        if case['graph_eligible']:
            IntentCandidate.model_validate(case['reference_intent'])
            snapshot_ref=reference(case['reference_intent'],facts)
            refs.append({'id':case['id'],'family_id':case['family_id'],'primary':case['primary'],
                'category':case['category'],'intent':case['reference_intent'],
                'draft_expected':case['expected_graph_outcome'],'snapshot_reference':snapshot_ref,
                'draft_snapshot_agree':case['expected_graph_outcome']==snapshot_ref['decision']})
    if not args.resume:save(out/'reference_graph_plan.json',{'assigned_before_verifier_calls':True,'cases':refs,
        'eligible_prompts':len(refs),'ineligible_prompts':400-len(refs),
        'ineligible_cases':[{'id':c['id'],'reason':c['expected_validation_outcome'],'draft_expected':c['expected_graph_outcome']} for c in cases if not c['graph_eligible']]})
    assert len(refs)==220
    if not all(r['draft_snapshot_agree'] for r in refs):
        report['metadata']['completion_status']='blocked_reference_snapshot_drift';save(path,report)
        raise RuntimeError('Draft and fresh snapshot disagree; references were not changed to match outputs')
    completed_B={r['id'] for r in report['reference_graph_results']}
    for r in refs:
        if r['id'] in completed_B:continue
        journal(out/'graph_events.jsonl',{'event':'reference_started','id':r['id'],'started_at_utc':utc()})
        measured=graph_call(r['intent'])
        row={**r,**measured,'graph_key':list(graph_key(r['intent'])),
            'decision_match':measured['actual']['decision']==r['draft_expected'],
            'evidence_match':evidence_matches(measured['actual'],r['snapshot_reference'],r['intent']['action'])}
        journal(out/'graph_events.jsonl',{'event':'reference_completed','record':row})
        report['reference_graph_results'].append(row);save(path,report)
        if len(report['reference_graph_results'])%40==0:print(f"Reference graph: {len(report['reference_graph_results'])}/220 saved",flush=True)
    close_driver()
    observer=Observer(out,intent_parser._client)
    captured=saved_interpretations(out/'interpretations.jsonl')
    completed={r['id'] for r in report['results']}
    report['metadata']['completion_status']='running_model_and_pipeline';save(path,report)
    consecutive_errors=0
    try:
        with patch.object(intent_parser,'_client',observer.client):
            for case in cases:
                if case['id'] in completed:continue
                if (out/'STOP_REQUESTED').exists():
                    report['metadata']['completion_status']='stopped_by_request';break
                observer.case_id=case['id'];observer.attempts=[];observer.extra_wait=0
                if case['id'] in captured:
                    prior=captured[case['id']];started=prior['started_at_utc'];elapsed=prior['wall_latency_ms']
                    resolution=IntentResolution.model_validate(prior['resolution'])
                    resolved=prior['resolution'];observer.attempts=prior['provider_attempts']
                else:
                    started=utc();start=time.perf_counter()
                    resolution=await intent_parser.parse_intent(case['query'])
                    elapsed=round((time.perf_counter()-start)*1000,3)
                    resolved=resolution.model_dump(mode='json')
                    # A graph failure must not cause a second model call on resume.
                    journal(out/'interpretations.jsonl',{'id':case['id'],'started_at_utc':started,
                        'resolution':resolved,'wall_latency_ms':elapsed,'provider_attempts':observer.attempts})
                raw=None;valid_json=False
                success=[a for a in observer.attempts if a.get('success')]
                if success:
                    try:raw=json.loads(success[-1]['raw_text']);valid_json=True
                    except (ValueError,TypeError):pass
                fields=field_checks(case.get('reference_intent'),resolved.get('intent'))
                status_match=resolved['status']==case['expected_validation_outcome']
                missing_match=set(case['expected_missing_fields']).issubset(resolution.missing_fields)
                fields_required=case['expected_validation_outcome'] in {'APPROVED','NEEDS_CLARIFICATION'}
                required_fields_match=(all(v['matches'] for v in fields.values()) if fields else False) if fields_required else None
                a={'actual':resolved,'latency_ms':elapsed,'raw_extraction':raw,'raw_valid_json':valid_json,
                    'raw_json_object':isinstance(raw,dict),'raw_prompt_schema_conformant':raw_shape(raw),
                    'provider_attempts':list(observer.attempts),'field_checks':fields,'fields_required_for_joint':fields_required,
                    'status_match':status_match,'missing_fields_match':missing_match,
                    'required_fields_match':required_fields_match,
                    'joint_reference_match':bool(status_match and missing_match and required_fields_match is not False)}
                calls=[];real_verify=pipeline.verify_intent
                def measured_verify(*vargs,**vkwargs):
                    t=time.perf_counter();result=real_verify(*vargs,**vkwargs)
                    calls.append({'input':vargs,'actual':dict(result),'wall_latency_ms':round((time.perf_counter()-t)*1000,3),
                        'operational_failure':result.get('reason')=='Authoritative graph knowledge is temporarily unavailable.'})
                    return result
                start=time.perf_counter()
                try:
                    with patch.object(pipeline,'parse_intent',AsyncMock(return_value=resolution)),patch.object(pipeline,'verify_intent',measured_verify):
                        final=await pipeline.process_prompt(PromptRequest(prompt=case['query'],new_operation=True))
                    final.pop('verification_id',None);final.pop('conversation_id',None)
                except Exception as exc:final={'decision':'ERROR','error_type':type(exc).__name__}
                pipeline_ms=round((time.perf_counter()-start)*1000,3)
                expected_final=case['expected_graph_outcome'] if case['graph_eligible'] else case['expected_validation_outcome']
                c={'actual':final,'expected_final':expected_final,'status_match':final['decision']==expected_final,
                    'joint_reference_match':a['joint_reference_match'] and final['decision']==expected_final,
                    'improper_approval':expected_final!='APPROVED' and final['decision']=='APPROVED',
                    'graph_calls':calls,'pipeline_after_recorded_interpretation_ms':pipeline_ms,
                    'combined_observed_stage_ms':elapsed+pipeline_ms,
                    'earliest_mismatch':('interpretation_or_validation' if not a['joint_reference_match'] else
                        'graph_or_reference' if final['decision']!=expected_final else None)}
                report['results'].append({'id':case['id'],'family_id':case['family_id'],'primary':case['primary'],
                    'category':case['category'],'query':case['query'],'started_at_utc':started,'completed_at_utc':utc(),
                    'expected_validation':case['expected_validation_outcome'],'A':a,'C':c})
                report['metrics']=summary(report);report['metadata']['last_checkpoint_utc']=utc();save(path,report)
                print(f"[{len(report['results'])}/400] {case['id']} A={resolved['status']} C={final['decision']} A_match={status_match} C_match={c['status_match']}",flush=True)
                consecutive_errors=consecutive_errors+1 if resolved['status']=='ERROR' else 0
                if consecutive_errors>=3:
                    report['metadata']['completion_status']='stopped_consecutive_service_errors';break
                if len(report['results'])<400:await asyncio.sleep(max(args.delay,observer.extra_wait))
        if len(report['results'])==400:report['metadata']['completion_status']='complete'
    except BaseException:
        report['metadata']['completion_status']='interrupted';raise
    finally:
        report['metadata']['last_checkpoint_utc']=utc();report['metrics']=summary(report);save(path,report);close_driver()
    after=snapshot();save(out/'snapshot-after.json',after)
    before=json.loads((out/'snapshot-before.json').read_bytes())
    report['metadata']['snapshot_content_unchanged']=stable_snapshot(before)==stable_snapshot(after)
    report['metadata']['protected_files_unchanged']=all(digest((ROOT/name).read_bytes())==value for name,value in protected.items())
    report['metadata']['production_code_unchanged']=all(digest((ROOT/name).read_bytes())==value for name,value in code.items())
    report['metadata']['completed_at_utc']=utc();save(path,report)
    print(json.dumps({'status':report['metadata']['completion_status'],'metrics':report['metrics']},indent=2),flush=True)
    return 0 if report['metadata']['completion_status']=='complete' else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    parser.add_argument('--output-root',type=Path,default=ROOT/'.cache/evaluation-runs/400_prompts')
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--allow-unreviewed',action='store_true')
    parser.add_argument('--delay',type=float,default=8)
    args=parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:return asyncio.run(run(args))
    finally:close_driver()


if __name__=='__main__':raise SystemExit(main())
