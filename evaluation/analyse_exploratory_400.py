"""Offline analysis of the separate 400-prompt exploratory run."""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cache/evaluation-tools'))
from evaluation.exploratory_400_runner import flatten, summary
from evaluation.graph_runner import timing
from core.slippage import parse_slippage


def write_json(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def csv_table(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def md_table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
        ['| '+' | '.join(str(v).replace('|','\\|') for v in row)+' |' for row in rows])


def key_resolution(row):
    value=row['A']['actual'];intent=dict(value.get('intent') or {})
    if intent.get('amount') is not None:intent['amount']=str(Decimal(intent['amount']).normalize())
    return json.dumps({'status':value['status'],'intent':intent,'missing_fields':sorted(value['missing_fields'])},sort_keys=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    args=parser.parse_args();out=args.folder
    report=json.loads((out/'results.json').read_bytes());dataset=json.loads((out/'dataset_snapshot.json').read_bytes())
    expected={r['id']:r for r in flatten(dataset)};rows=report['results'];metrics=summary(report)
    metrics['run_status']=report['metadata']['completion_status']
    metrics['case_count_actual']=len(rows);metrics['case_count_planned']=400
    metrics['final_held_out_evaluation']=False
    metrics['dataset_sha256']=hashlib.sha256((out/'dataset_snapshot.json').read_bytes()).hexdigest()
    metrics['validation_confusion']=[{'expected':a,'actual':b,'cases':n} for (a,b),n in Counter((r['expected_validation'],r['A']['actual']['status']) for r in rows).items()]
    metrics['pipeline_confusion']=[{'expected':a,'actual':b,'cases':n} for (a,b),n in Counter((r['C']['expected_final'],r['C']['actual']['decision']) for r in rows).items()]
    metrics['graph_confusion']=[{'expected':a,'actual':b,'cases':n} for (a,b),n in Counter((r['draft_expected'],r['actual']['decision']) for r in report['reference_graph_results']).items()]
    attempts=[a for r in rows for a in r['A']['provider_attempts']]
    metrics['provider']={'observed_outer_attempts':len(attempts),'successful_responses':sum(a.get('success',False) for a in attempts),
        'failed_outer_attempts':sum(not a.get('success',False) for a in attempts),
        'usage_tokens':{k:sum((a.get('usage') or {}).get(k,0) or 0 for a in attempts) for k in ['prompt_tokens','completion_tokens','total_tokens']},
        'http_attempts_in_sdk':'not individually observed','billing_cost':'not measured'}
    if rows:
        metrics['interpretation_timing_not_R6']=timing([{'wall_latency_ms':r['A']['latency_ms']} for r in rows])
    metrics['returned_candidates']=sum(r['A']['actual'].get('intent') is not None for r in rows)
    fields=defaultdict(list)
    for r in rows:
        if r['A']['fields_required_for_joint']:
            for name,check in (r['A']['field_checks'] or {}).items():fields[name].append(check['matches'])
    metrics['normalized_field_matches_required_subset']={name:{'matches':sum(v),'cases':len(v)} for name,v in fields.items()}
    family=defaultdict(list)
    for r in rows:family[r['family_id']].append(r)
    pairs=[]
    for name,members in sorted(family.items()):
        if len(members)!=2:continue
        a,b=members
        pairs.append({'family_id':name,'validation_status_same':a['A']['actual']['status']==b['A']['actual']['status'],
            'normalized_resolution_same':key_resolution(a)==key_resolution(b),
            'pipeline_status_same':a['C']['actual']['decision']==b['C']['actual']['decision'],
            'both_joint_reference_matches':a['C']['joint_reference_match'] and b['C']['joint_reference_match']})
    metrics['paired_formulations']={'complete_pairs':len(pairs),**{k:sum(p[k] for p in pairs) for k in ['validation_status_same','normalized_resolution_same','pipeline_status_same','both_joint_reference_matches']}}
    errors=[];flags=[]
    for r in rows:
        a=r['A'];c=r['C'];fields_bad=[k for k,v in (a['field_checks'] or {}).items() if not v['matches']]
        if a['actual']['status']=='ERROR':kind='provider_or_parser_failure'
        elif c['improper_approval']:kind='pipeline_approval_against_nonapproval_draft_reference'
        elif not a['status_match']:kind='validation_disposition_mismatch_requires_reference_review'
        elif a['fields_required_for_joint'] and fields_bad:kind='interpreted_field_mismatch'
        elif not a['missing_fields_match']:kind='clarification_field_mismatch'
        elif not c['status_match']:kind='graph_or_final_disposition_mismatch'
        else:kind='reference_match'
        if kind!='reference_match':errors.append({'id':r['id'],'family_id':r['family_id'],'primary':r['primary'],
            'category':r['category'],'classification':kind,'query':r['query'],'expected_A':r['expected_validation'],
            'actual_A':a['actual']['status'],'expected_C':c['expected_final'],'actual_C':c['actual']['decision'],
            'fields_mismatching':','.join(fields_bad),'error_code':a['actual'].get('error_code')})
        if c['improper_approval'] or (a['actual']['status']=='APPROVED' and not a['joint_reference_match']):
            flags.append({'id':r['id'],'query':r['query'],'category':r['category'],
                'draft_reference':expected[r['id']],'raw_extraction':a['raw_extraction'],
                'normalized_resolution':a['actual'],'pipeline':c['actual'],
                'pipeline_improper_approval_flag':c['improper_approval'],
                'semantic_graph_containment':bool(c['graph_calls']) and c['actual']['decision']!='APPROVED' and not any(g['operational_failure'] for g in c['graph_calls']),
                'review_status':'assistant diagnostic; human adjudication required; no execution tested'})
    metrics['diagnostic_categories']=dict(Counter(e['classification'] for e in errors))
    metrics['flagged_interpretation_approvals']=sum(r['A']['actual']['status']=='APPROVED' and not r['A']['joint_reference_match'] for r in rows)
    metrics['semantic_graph_containment']=sum(r['semantic_graph_containment'] for r in flags)
    graph=report['reference_graph_results'];primary_graph=[r for r in graph if r['primary']]
    metrics['reference_graph']['primary_eligible_prompts']=len(primary_graph)
    metrics['reference_graph']['primary_timing']=timing(primary_graph) if primary_graph else None
    metrics['reference_graph']['slow_requests']=[{'id':r['id'],'ms':r['wall_latency_ms']} for r in graph if r['wall_latency_ms']>2000]
    write_json(out/'analysis.json',metrics);write_json(out/'approval_flags_for_review.json',flags)
    csv_table(out/'diagnostics.csv',errors);csv_table(out/'paired_formulations.csv',pairs)
    csv_table(out/'case_summary.csv',[{'id':r['id'],'family_id':r['family_id'],'primary':r['primary'],'category':r['category'],
        'expected_validation':r['expected_validation'],'actual_validation':r['A']['actual']['status'],'validation_match':r['A']['status_match'],
        'expected_pipeline':r['C']['expected_final'],'actual_pipeline':r['C']['actual']['decision'],'pipeline_status_match':r['C']['status_match'],
        'joint_draft_match':r['C']['joint_reference_match'],'interpretation_ms':r['A']['latency_ms'],
        'graph_calls':len(r['C']['graph_calls']),'improper_approval_flag':r['C']['improper_approval']} for r in rows])
    csv_table(out/'graph_summary.csv',[{'id':r['id'],'family_id':r['family_id'],'primary':r['primary'],'category':r['category'],
        'expected':r['draft_expected'],'actual':r['actual']['decision'],'decision_match':r['decision_match'],
        'evidence_match':r['evidence_match'],'operational_failure':r['operational_failure'],'latency_ms':r['wall_latency_ms']} for r in graph])
    totals=md_table(['Population','Prompts','Validation status matches','Pipeline status matches','Joint draft matches','Provider/parser errors','Draft pipeline approval flags'],
        [(name,v['prompts'],v['validation_status_matches'],v['pipeline_status_matches'],v['joint_reference_matches'],v['validation_errors'],v['draft_pipeline_improper_approvals']) for name,v in [('All saved prompts',metrics['all_prompts']),('Primary formulations',metrics['primary_formulations'])]])
    categories=md_table(['Category','Prompts','A status matches','C status matches','Joint draft matches'],[(k,v['prompts'],v['validation_status_matches'],v['pipeline_status_matches'],v['joint_reference_matches']) for k,v in metrics['by_category'].items()])
    t=metrics['reference_graph']
    timing_rows=[(name,v['requests'],v['within_2000_ms'],f"{v['percentage_within_2000_ms']:.6f}%",v['p50_ms'],v['p95_ms'],v['max_ms'])
        for name,v in [('All eligible prompt references',t['timing_all']),('Primary eligible references',t['primary_timing']),('First distinct input',t['timing_first_distinct'])] if v]
    timings=md_table(['Graph population','Calls','≤2,000 ms','Percentage','p50 ms','p95 ms','Max ms'],timing_rows)
    graph_confusion=md_table(['Draft graph reference','Observed decision','Calls'],[(r['expected'],r['actual'],r['cases']) for r in metrics['graph_confusion']])
    metadata=report['metadata'];pairs_m=metrics['paired_formulations']
    quota_cases=[r['id'] for r in rows if r['A']['actual']['status']=='ERROR' and
        any('tokens_per_day' in a.get('rate_limit_scope',[]) for a in r['A']['provider_attempts'])]
    metrics['daily_quota_failure_cases']=quota_cases
    slippage_blocked=[]
    for r in rows:
        if (r['category']=='supported_uniswap' and
                'unrecognized_slippage_condition' in r['A']['actual'].get('unhandled_constraints',[])):
            extracted=(r['A']['raw_extraction'] or {}).get('slippage')
            try: raw_bps=parse_slippage(extracted)
            except (ValueError,TypeError): raw_bps=None
            ref_bps=(expected[r['id']].get('reference_intent') or {}).get('slippage_bps')
            slippage_blocked.append({'id':r['id'],'raw_slippage_bps':raw_bps,
                'reference_slippage_bps':ref_bps,'raw_slippage_matches':raw_bps is not None and raw_bps==ref_bps})
    metrics['supported_swaps_blocked_by_slippage_wording']=slippage_blocked
    flash_flags=[r['id'] for r in rows if 'flash borrow' in r['query'].lower() and
        r['C']['improper_approval']]
    metrics['flash_borrow_pipeline_approval_flags']=flash_flags
    metrics['run_timestamps']={k:metadata.get(k) for k in
        ['started_at_utc','resumed_at_utc','last_checkpoint_utc','completed_at_utc']}
    write_json(out/'analysis.json',metrics)
    body=f'''# Exploratory 400-prompt evaluation — started 19 October 2026

**Status: {metadata['completion_status']}. Saved model/pipeline results: {len(rows)}/400.**
This is one exploratory pass over the assistant-drafted proposal. It is not the
final held-out A–C evaluation. The researcher requested execution while reference
review and family-independence checks remained pending. All reference labels were
preserved and snapshotted before execution. This dataset is now exposed evaluation
material; do not describe a later rerun as a previously untouched held-out test.

Started (UTC): `{metadata['started_at_utc']}`.
Resumed (UTC): `{metadata.get('resumed_at_utc',[])}`.
Latest checkpoint (UTC): `{metadata.get('last_checkpoint_utc')}`.
The run stopped after 294 cases on 19 October when the daily provider token
quota was exhausted, and resumed on 20 October from case 295. Previously saved
cases were not repeated. Daily-quota failure cases retained in the denominator:
`{quota_cases}`. Segment checkpoints and graph snapshots are preserved.

## Scope and method

Groq model `{metadata['model']}`, temperature 0, reasoning effort low; Sepolia
11155111. The unchanged parser is called once logically per prompt, with its
normal retry behavior. Its recorded resolution is reused in the unchanged pipeline;
there is no second model call for C. Primary formulations run first, followed by
alternate formulations. Temporal ordering can confound a wording comparison.

Independent reference-intent graph checks precede extraction and cover 220 eligible
prompts, 110 nominal primary families and 86 distinct graph inputs. The remaining
180 prompts are ineligible by the draft validation reference; their reasons are
saved in `reference_graph_plan.json`. Graph results are not gated by LLM success.

No wallet checks, graph mutations, policy renewal, signing or transaction submission
are part of this run. Graph approval is not wallet readiness or execution success.

## Interpretation and pipeline conformance

{totals}

{categories}

“Joint draft match” requires both stage dispositions and the specified normalized
fields/missing fields for APPROVED or NEEDS_CLARIFICATION references. For other
dispositions it measures disposition conformance only, not exhaustive understanding
of all conditions. It must not be called independently established end-to-end
accuracy. Detailed raw outputs, normalized candidates, field comparisons and
graph calls are in `results.json`; `case_summary.csv` provides a flat table.

Valid JSON objects: {metrics['all_prompts']['json_objects']}/{len(rows)}.
Strict prompt-shape conformance: {metrics['all_prompts']['prompt_schema_conformant']}/{len(rows)}.
Returned normalized candidates: {metrics['returned_candidates']}; omitted candidates
after a non-approval are not automatically schema errors. The shape audit checks
the advertised extraction format without modifying the production parser.

Observed provider outer attempts: {metrics['provider']['observed_outer_attempts']};
successful responses: {metrics['provider']['successful_responses']}; failed outer
attempts: {metrics['provider']['failed_outer_attempts']}. SDK-internal HTTP retries
are not individually counted. Recorded tokens: {metrics['provider']['usage_tokens']}.
This is not a monetary billing statement. All failures remain visible.

## Independent graph results and R6

Recorded graph calls: {t['completed']}; draft decision matches:
{t['draft_decision_matches']}; selected snapshot evidence matches:
{t['snapshot_evidence_matches']}; operational failures: {t['operational_failures']}.
The draft and current snapshot dispositions were compared before verifier calls.
Snapshot conformance is not independent protocol truth.

{graph_confusion}

{timings}

Timings include the verifier and database work, excluding LLM and wallet time.
First and slow calls are retained; no cache flush was performed. Quantiles use
nearest rank. A Windows checkpoint replacement failure interrupted the graph
phase after 100 measurements. All 100 were recovered intact from the checkpoint
and its fully written temporary file; none was rerun or discarded. The remaining
graph calls resumed after a process restart, which affects connection/cache state.
Recovery artifacts and harness hashes are retained. Production code and labels
were not altered to improve results.

## Alternative wording and diagnostics

Completed pairs: {pairs_m['complete_pairs']}/200. Same A status:
{pairs_m['validation_status_same']}; same normalized resolution:
{pairs_m['normalized_resolution_same']}; same C status:
{pairs_m['pipeline_status_same']}; both wordings jointly match the draft:
{pairs_m['both_joint_reference_matches']}. Matching outcomes may both be wrong.
No three-pass model repeatability experiment was performed.

Diagnostic counts: {metrics['diagnostic_categories']}.
Flagged interpretation approvals: {metrics['flagged_interpretation_approvals']};
non-operational graph containment among recorded flags:
{metrics['semantic_graph_containment']}. Containment is not correct interpretation.
Review every flag in `approval_flags_for_review.json` and other discrepancies in
`diagnostics.csv`. These labels are not independently adjudicated safety failures.

### Observed causes and reference-review priorities

- {len(slippage_blocked)} supported-swap draft cases were blocked with
  `unrecognized_slippage_condition`; raw model slippage matched the draft in
  {sum(v['raw_slippage_matches'] for v in slippage_blocked)} of these cases.
  The phrase "slippage must not exceed" is absent from the deterministic
  recognition patterns in `llm/request_constraints.py`. This is a validation
  wording limitation, not evidence that the model failed to extract that value.
- Families 127 and 128 use "add liquidity" and "remove liquidity" in an Aave
  request. The primary outputs map these to supply and withdraw, whereas the
  draft expects UNSUPPORTED. The intended meaning and labels need human
  adjudication before calling these confirmed false approvals.
- Flash-borrow prompts approved against unsupported draft references:
  `{flash_flags}`. In FINAL-DRAFT-126-B, the raw extraction replaced "flash borrow"
  with ordinary `borrow`, and the graph approved the resulting borrow intent.
  This illustrates that relationship verification can accept a valid graph path
  after the language stage has lost an unsupported action modifier. No wallet
  operation was attempted.
- Some incomplete requests retain the clarification disposition but lose
  specified fields; other ambiguous requests become UNSUPPORTED or REJECTED.
  The diagnostics separate field loss from disposition mismatches.
- Provider quota errors are availability outcomes, not semantic extraction
  failures. They remain in the attempted-prompt denominator.

These observations do not alter code or labels. A later correction must be
evaluated as a separate version, with any reuse of these prompts disclosed.

## Validity and remaining work

The 400 prompts represent 200 declared families, not 400 independent cases. The
earlier audit found 74 families sharing development graph inputs and only 86
distinct eligible graph inputs. Synthetic templates and reverse directions can
remain dependent. No valid population confidence interval or final false-approval
hypothesis test is claimed. Final evaluation requires researcher-reviewed,
appropriately separated references and a supervisor-approved sampling plan.

Graph snapshot content unchanged: {metadata.get('snapshot_content_unchanged','not checked yet')}.
Protected environment/policy files unchanged: {metadata.get('protected_files_unchanged','not checked yet')}.
Production/evaluation code hash check: {metadata.get('production_code_unchanged','not checked yet')}.
Earlier thesis-report artifacts were preserved; this run is a separate supplement.

## Reproduction

Input dataset SHA-256: `{metrics['dataset_sha256']}`.
Run parameters, timestamps, code hashes and original labels are preserved here.
Regenerate analysis without model/database calls from the repository root:

```powershell
python -B -m evaluation.analyse_exploratory_400 {out.as_posix()}
```

The execution command is `python -B -m evaluation.exploratory_400_runner
--allow-unreviewed --delay 8`; it makes model calls and must not be confused with
offline analysis. The immutable previous report ZIP remains unchanged.
'''
    if rows:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        figure_dir=out/'figures';figure_dir.mkdir(exist_ok=True)
        states=['APPROVED','REJECTED','UNSUPPORTED','NEEDS_CLARIFICATION','INSUFFICIENT_EVIDENCE','ERROR']
        for name,title in [('validation_confusion','Interpretation / validation'),('pipeline_confusion','Pipeline disposition')]:
            counts={(r['expected'],r['actual']):r['cases'] for r in metrics[name]}
            matrix=np.array([[counts.get((a,b),0) for b in states] for a in states])
            fig,ax=plt.subplots(figsize=(8.5,6))
            im=ax.imshow(matrix,cmap='Blues')
            ax.set_xticks(range(len(states)),[s.replace('_','\n') for s in states],rotation=25,ha='right',fontsize=8)
            ax.set_yticks(range(len(states)),[s.replace('_','\n') for s in states],fontsize=8)
            ax.set(xlabel='Observed outcome',ylabel='Draft expected outcome',title=f'{title}: {len(rows)} exploratory prompts\nUnreviewed references; not final held-out accuracy')
            for i in range(len(states)):
                for j in range(len(states)):
                    ax.text(j,i,str(matrix[i,j]),ha='center',va='center',color='white' if matrix[i,j]>matrix.max()/2 else 'black')
            fig.colorbar(im,ax=ax,label='Prompts');fig.tight_layout()
            fig.savefig(figure_dir/f'{name}.png',dpi=180);fig.savefig(figure_dir/f'{name}.svg');plt.close(fig)
        fig,ax=plt.subplots(figsize=(8,4.5));distinct={}
        for r in graph:distinct.setdefault(tuple(r['graph_key']),r)
        for label,values in [('All eligible references (220)',graph),('First distinct input (86)',list(distinct.values()))]:
            xs=sorted(r['wall_latency_ms'] for r in values)
            ax.step(xs,[100*(i+1)/len(xs) for i in range(len(xs))],where='post',label=label)
        ax.axvline(2000,color='#b91c1c',linestyle='--',label='2,000 ms threshold');ax.axhline(95,color='#666',linestyle=':')
        ax.set_xscale('log');ax.set(xlabel='Verification wall time (ms)',ylabel='Completed requests (%)',ylim=(0,102),title='Exploratory reference graph latency\nFirst and slow calls retained; checkpoint recovery disclosed')
        ax.legend(loc='lower right');fig.tight_layout();fig.savefig(figure_dir/'graph_latency.png',dpi=180);fig.savefig(figure_dir/'graph_latency.svg');plt.close(fig)
        body+='\n## Figures\n\n![Validation confusion](figures/validation_confusion.png)\n\n![Pipeline confusion](figures/pipeline_confusion.png)\n\n![Graph latency](figures/graph_latency.png)\n'
    (out/'SUMMARY.md').write_text(body,encoding='utf-8')
    print(json.dumps({'status':metadata['completion_status'],'all':metrics['all_prompts'],'primary':metrics['primary_formulations'],'graph':t,'pairs':pairs_m},indent=2))


if __name__=='__main__':main()
