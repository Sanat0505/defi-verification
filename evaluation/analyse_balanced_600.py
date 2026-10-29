"""Offline analysis of complete or partial balanced-600 checkpoints."""
import argparse
import csv
import json
from pathlib import Path


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def binary_counts(rows):
    counts = dict(TP=0, FP=0, FN=0, TN=0, operational_errors=0, abstentions=0)
    for row in rows:
        if row['operational_error']:
            counts['operational_errors'] += 1
        elif row['actual_pipeline'] == 'INSUFFICIENT_EVIDENCE':
            counts['abstentions'] += 1
        elif row['actual_pipeline'] == 'APPROVED':
            counts['TP' if row['expected_pipeline'] == 'APPROVED' else 'FP'] += 1
        else:
            counts['FN' if row['expected_pipeline'] == 'APPROVED' else 'TN'] += 1
    tp, fp, fn, tn = (counts[k] for k in ['TP', 'FP', 'FN', 'TN'])
    decisions = tp + fp + fn + tn
    return dict(**counts, decision_denominator=decisions,
                decision_coverage=ratio(decisions, len(rows)),
                precision=ratio(tp,tp+fp), recall=ratio(tp,tp+fn),
                specificity=ratio(tn,tn+fp), false_positive_rate=ratio(fp,fp+tn),
                false_negative_rate=ratio(fn,fn+tp), f1=ratio(2*tp,2*tp+fp+fn),
                binary_accuracy=ratio(tp+tn,decisions))


def csv_write(path, rows):
    if not rows:
        return
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def analyse(folder):
    # The runner replaces this file atomically; analysis uses one consistent read.
    report=json.loads((folder/'results.json').read_bytes())
    rows=[]
    for r in report['results']:
        a,c=r['A'],r['C']
        operational=a['actual']['status']=='ERROR' or c['actual']['decision']=='ERROR' or any(
            call.get('operational_failure') for call in c['graph_calls'])
        rows.append(dict(id=r['id'],family_id=r['family_id'],primary=r['primary'],category=r['category'],
                         expected_validation=r['expected_validation'],actual_validation=a['actual']['status'],
                         expected_pipeline=c['expected_final'],actual_pipeline=c['actual']['decision'],
                         exact_status_match=c['status_match'],joint_reference_match=c['joint_reference_match'],
                         operational_error=bool(operational),interpretation_ms=a['latency_ms'],
                         graph_calls=len(c['graph_calls']),earliest_mismatch=c['earliest_mismatch']))
    graph=[dict(id=r['id'],family_id=r['family_id'],primary=r['primary'],category=r['category'],
                expected=r['draft_expected'],actual=r['actual']['decision'],decision_match=r['decision_match'],
                evidence_match=r['evidence_match'],operational_failure=r['operational_failure'],
                latency_ms=r['wall_latency_ms']) for r in report['reference_graph_results']]
    unique={}
    for r in report['reference_graph_results']:
        unique.setdefault(tuple(r['graph_key']),r)
    def graph_group(values):
        return dict(calls=len(values),decision_matches=sum(r['decision_match'] for r in values),
                    evidence_matches=sum(r['evidence_match'] for r in values),
                    operational_failures=sum(r['operational_failure'] for r in values),
                    within_two_seconds=sum(r['wall_latency_ms']<=2000 for r in values),
                    max_ms=max((r['wall_latency_ms'] for r in values),default=None))
    def group(values):
        return dict(attempted=len(values),exact_status_matches=sum(r['exact_status_match'] for r in values),
                    exact_status_agreement=ratio(sum(r['exact_status_match'] for r in values),len(values)),
                    joint_matches=sum(r['joint_reference_match'] for r in values),binary=binary_counts(values))
    planned=report['metadata']['logical_model_calls_planned']
    metrics=dict(status=report['metadata']['completion_status'],checkpoint_utc=report['metadata'].get('last_checkpoint_utc'),
                 planned_prompts=planned,attempted=len(rows),unattempted=planned-len(rows),
                 all_attempted=group(rows),primary_formulations=group([r for r in rows if r['primary']]),
                 by_category={c:group([r for r in rows if r['category']==c]) for c in sorted({r['category'] for r in rows})},
                 graph_all=graph_group(report['reference_graph_results']),graph_first_distinct=graph_group(list(unique.values())),
                 reference_review='User accepted execution; item-level human review is not documented.',
                 limitation='Agreement with assistant-drafted references, not independent protocol truth. Shared inputs and paraphrases are not independent samples.',
                 joint_definition=report.get('metrics',{}).get('joint_reference_match_definition'))
    (folder/'analysis.json').write_text(json.dumps(metrics,indent=2)+'\n',encoding='utf-8')
    csv_write(folder/'case_summary.csv',rows);csv_write(folder/'graph_summary.csv',graph)
    csv_write(folder/'diagnostics.csv',[r for r in rows if not r['joint_reference_match']])
    a=metrics['all_attempted'];b=a['binary'];g=metrics['graph_all']
    text=f'''# Balanced 600-prompt evaluation status

Checkpoint: {metrics['checkpoint_utc']}. Status: **{metrics['status']}**.

**{len(rows)}/{planned} prompts attempted; {planned-len(rows)} unattempted.**
Do not describe a partial checkpoint as a completed 600-prompt result.

- Exact pipeline status matches: {a['exact_status_matches']}/{len(rows)} attempted prompts.
- Joint reference matches: {a['joint_matches']}/{len(rows)} attempted prompts.
- Binary decisions: TP {b['TP']}, FP {b['FP']}, FN {b['FN']}, TN {b['TN']}.
- Operational errors: {b['operational_errors']}; evidence abstentions: {b['abstentions']}.
- Independent reference-intent graph checks: {g['calls']}/340; {len(unique)} distinct inputs observed.
- Graph decision matches: {g['decision_matches']}/{g['calls']}; within two seconds: {g['within_two_seconds']}/{g['calls']}.

The user accepted this dataset for execution. Item-level human reference review
is not documented. Labels remain assistant-drafted. This is a development-informed
balanced follow-up, not a demonstrated untouched, independently reviewed benchmark.
The 600 prompts form 300 paired scenario instances, not 600 independent trials.
Graph conformance does not establish wallet readiness or transaction success.

Binary metrics exclude operational errors and evidence abstentions and report
decision coverage. All attempted prompts remain in exact-status denominators.
Unattempted prompts are not counted as semantic failures or correct negatives.
Joint matches use the definition in analysis.json; unsupported-condition semantics
still require review beyond status-only agreement.

No wallet calls or transaction submission are part of this run. Original
400-prompt results remain separate. Model: openai/gpt-oss-20b; one pass.
'''
    (folder/'SUMMARY.md').write_text(text,encoding='utf-8')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    analyse(parser.parse_args().folder)
