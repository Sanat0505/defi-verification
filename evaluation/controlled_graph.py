"""Controlled D/E experiments in a dedicated Neo4j database; no production writes.

Run from the repository root. The unchanged production verifier is injected with
an explicitly selected fixture session only inside unittest.mock.patch contexts.
References and fixture specifications are saved before verification begins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from source.core.config import settings
from source.db import sync, verifier
from source.db.connection import close_driver, get_driver
from source.db.graph_v2 import PROTOCOL_FUNCTIONS

OUT = ROOT / '.cache/evaluation-runs/controlled_graph'
DB = "thesis-eval-20261019"
OWNER = "thesis-controlled-20261019-v1"
MUTATIONS = {
    "action_function": ("function", "IMPLEMENTS_ACTION", "action"),
    "contract_function": ("contract", "EXPOSES_FUNCTION", "function"),
    "deployment_contract": ("deployment", "DEPLOYED_CONTRACT", "contract"),
    "resource_membership": ("deployment", None, "resource"),
    "resource_asset": ("resource", None, "token_in"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def query(cypher, **params):
    rows, _, _ = get_driver().execute_query(cypher, parameters_=params, database_=DB)
    return [dict(row) for row in rows]


def live_fingerprint():
    values = {}
    for name, cypher in {
        "nodes": "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props ORDER BY id",
        "relationships": "MATCH (a)-[r]->(b) RETURN elementId(r) AS id, elementId(a) AS a, type(r) AS type, elementId(b) AS b, properties(r) AS props ORDER BY id",
    }.items():
        rows, _, _ = get_driver().execute_query(cypher, database_="neo4j", routing_="r")
        rows = [dict(row) for row in rows]
        values[name] = {"count": len(rows), "sha256": digest(rows)}
    return values


def ensure_fixture_database():
    assert re.fullmatch(r"thesis-eval-[0-9]{8}", DB)
    assert DB not in {"neo4j", "system"}
    rows, _, _ = get_driver().execute_query("SHOW DATABASES YIELD name RETURN name", database_="system", routing_="r")
    if DB not in {r["name"] for r in rows}:
        get_driver().execute_query(f"CREATE DATABASE `{DB}` WAIT 30 SECONDS", database_="system")
    foreign = query("MATCH (n) WHERE n._eval_owner IS NULL OR n._eval_owner <> $owner RETURN count(n) AS count", owner=OWNER)[0]["count"]
    if foreign:
        raise RuntimeError("Fixture database contains foreign nodes; refusing to change it")


def clear_fixture():
    query("MATCH (n) WHERE n._eval_owner=$owner DETACH DELETE n", owner=OWNER)
    assert query("MATCH (n) RETURN count(n) AS count")[0]["count"] == 0


def fixture_specs(snapshot):
    specs = []
    contracts = snapshot["contracts"]
    for number, pool in enumerate(snapshot["pools"][:4], 1):
        ts = pool["tokens"]
        if len(ts) != 2:
            raise ValueError("A fixture pool must have two admitted token endpoints")
        specs.append({"id": f"UNI-{number:02}", "protocol": "Uniswap V3", "protocol_key": "uniswap-v3",
            "action": "swap", "token_in": ts[0], "token_out": ts[1], "resource": pool,
            "contract": next(c for c in contracts if c["role"] == "swap_router"),
            "quoter": next(c for c in contracts if c["role"] == "quoter")})
    for action in ["supply", "withdraw", "borrow", "repay"]:
        for symbol in ["USDC", "USDT"]:
            reserve = next(r for r in snapshot["reserves"] if r["symbol"] == symbol and action in r["actions"])
            specs.append({"id": f"AAVE-{action.upper()}-{symbol}", "protocol": "Aave V3", "protocol_key": "aave-v3",
                "action": action, "token_in": {"symbol":symbol,"address":reserve["address"],"decimals":reserve["decimals"]},
                "token_out": None, "resource": reserve,
                "contract": next(c for c in contracts if c["role"] == "pool" and c["action"] == action)})
    if len(specs) != 12:
        raise ValueError("Expected four swap and eight lending controls")
    return specs


def materialize(spec):
    clear_fixture()
    stamp = datetime.now(timezone.utc).isoformat()
    nodes, edges = [], []
    def node(node_id, label, **props):
        nodes.append({"key":node_id,"label":label,"props":{"_eval_id":node_id,"_eval_owner":OWNER,**props}})
    def edge(a, typ, b, **props):
        edges.append({"a":a,"type":typ,"b":b,"props":props})
    swap = spec["action"] == "swap"
    node("family", "ProtocolFamily", name=spec["protocol"])
    node("deployment", "ProtocolDeployment", key=f"{spec['protocol_key']}:11155111", verified=True, chain_id=11155111,
         last_successful_sync_at=stamp, last_sync_status="SUCCESS", pool_discovery_complete=True,
         asset_coverage="official-address-book-complete", source_url="fixture:admitted-snapshot-projection")
    node("action", "Action", name=spec["action"])
    node("contract", "Contract", address=spec["contract"]["address"], verified=True, chain_id=11155111,
         role="swap_router" if swap else "pool")
    fn = next(f for f in PROTOCOL_FUNCTIONS[spec["protocol_key"]] if f["action"] == spec["action"] and f["purpose"] == "execute")
    node("function", "Function", verified=True, purpose="execute", name=fn["name"], signature=fn["signature"], selector=fn["selector"])
    node("resource", "Pool" if swap else "Reserve", verified=True, active=True, verification_eligible=True,
         chain_id=11155111, address=spec["resource"].get("address", spec["id"]), fee=spec["resource"].get("fee"))
    for key in ["token_in", "token_out"]:
        if spec.get(key):
            t=spec[key]
            node(key,"Token",symbol=t["symbol"],address=t["address"],decimals=t["decimals"],verified=True,verification_eligible=True,chain_id=11155111)
    edge("family","HAS_DEPLOYMENT","deployment")
    edge("deployment","SUPPORTS_ACTION","action")
    edge("deployment","DEPLOYED_CONTRACT","contract",role="swap_router" if swap else "pool",active=True)
    edge("contract","EXPOSES_FUNCTION","function")
    edge("function","IMPLEMENTS_ACTION","action")
    edge("deployment","HAS_POOL" if swap else "HAS_RESERVE","resource",active=True)
    edge("resource","SUPPORTS_TOKEN" if swap else "UNDERLYING_ASSET","token_in")
    if swap:
        edge("resource","SUPPORTS_TOKEN","token_out")
        node("quoter","Contract",address=spec["quoter"]["address"],verified=True,chain_id=11155111,role="quoter")
        qf=next(f for f in PROTOCOL_FUNCTIONS['uniswap-v3'] if f['purpose']=='preflight')
        node("quote_function","Function",verified=True,purpose="preflight",name=qf['name'],signature=qf['signature'],selector=qf['selector'])
        edge("deployment","DEPLOYED_CONTRACT","quoter",active=True,role="quoter")
        edge("quoter","EXPOSES_FUNCTION","quote_function")
        edge("quote_function","IMPLEMENTS_ACTION","action")
    else:
        edge("resource","SUPPORTS_ACTION","action")
    for n in nodes:
        query(f"CREATE (n:{n['label']}) SET n=$props",props=n['props'])
    for e in edges:
        query(f"MATCH (a {{_eval_id:$a}}),(b {{_eval_id:$b}}) CREATE (a)-[r:{e['type']}]->(b) SET r=$props",a=e['a'],b=e['b'],props=e['props'])
    return {"nodes":nodes,"edges":edges}


def state():
    return {"nodes":query("MATCH (n) RETURN n._eval_id AS id, labels(n) AS labels, properties(n) AS props ORDER BY id"),
            "edges":query("MATCH (a)-[r]->(b) RETURN a._eval_id AS a,type(r) AS type,b._eval_id AS b,properties(r) AS props ORDER BY a,type,b")}


def delete_edge(spec, mutation):
    a, typ, b = MUTATIONS[mutation]
    if typ is None:
        typ = ("HAS_POOL" if spec['action']=='swap' else "HAS_RESERVE") if mutation=='resource_membership' else ("SUPPORTS_TOKEN" if spec['action']=='swap' else "UNDERLYING_ASSET")
    n=query(f"MATCH (a {{_eval_id:$a}})-[r:{typ}]->(b {{_eval_id:$b}}) DELETE r RETURN count(r) AS count",a=a,b=b)[0]['count']
    assert n==1, (mutation,n)
    return {'from':a,'relationship':typ,'to':b,'deleted_count':n}


def arguments(spec):
    return dict(protocol=spec['protocol'],token_in=spec['token_in']['symbol'],token_out=(spec.get('token_out') or {}).get('symbol'),action=spec['action'],chain_id=11155111)


def entity_baseline(spec):
    """Same admitted fixture entities and freshness; deliberately no edge traversal.

    Deployment metadata identifies scope. Node properties test action, role,
    function identity, trust, active resource and ERC-20 metadata. This comparator
    intentionally cannot establish that the entities are connected.
    """
    started=time.perf_counter()
    nodes={r['id']:r['props'] for r in query('MATCH (n) RETURN n._eval_id AS id, properties(n) AS props')}
    d=nodes.get('deployment',{})
    fresh,_=verifier._freshness(d)
    if not fresh:
        decision='INSUFFICIENT_EVIDENCE'
    else:
        required=['family','deployment','action','contract','function','resource','token_in']
        if spec['action']=='swap': required+=['quoter','quote_function','token_out']
        ok=all(k in nodes for k in required)
        ok=ok and d.get('chain_id')==settings.supported_chain_id and d.get('verified') is True
        ok=ok and nodes['family'].get('name')==spec['protocol'] and nodes['action'].get('name')==spec['action']
        ok=ok and all(nodes[k].get('verified') is True for k in required if k not in ['family','action'])
        ok=ok and nodes['resource'].get('active') is True and nodes['function'].get('purpose')=='execute'
        ok=ok and nodes['function'].get('signature')==spec['contract']['signature']
        for key in ['token_in','token_out']:
            if spec.get(key):
                ok=ok and nodes[key].get('chain_id')==11155111 and nodes[key].get('symbol')==spec[key]['symbol'] and nodes[key].get('decimals') is not None
        if spec['action']=='swap':
            ok=ok and all(nodes[k].get('verification_eligible') is True for k in ['resource','token_in','token_out'])
            ok=ok and nodes['contract'].get('role')=='swap_router' and nodes['quoter'].get('role')=='quoter'
            ok=ok and nodes['quote_function'].get('purpose')=='preflight' and nodes['resource'].get('fee') is not None
            ok=ok and nodes['token_in'].get('address')!=nodes['token_out'].get('address')
        else: ok=ok and nodes['contract'].get('role')=='pool'
        complete=d.get('pool_discovery_complete') is True if spec['action']=='swap' else d.get('asset_coverage')=='official-address-book-complete'
        decision='APPROVED' if ok else ('REJECTED' if complete else 'INSUFFICIENT_EVIDENCE')
    return {'decision':decision,'wall_latency_ms':round((time.perf_counter()-started)*1000,3),'method':'entity_properties_without_relationship_traversal'}


def verify(spec, unavailable=False):
    def fail():
        from neo4j.exceptions import ServiceUnavailable
        raise ServiceUnavailable('Controlled fixture-only connection failure')
    session=fail if unavailable else lambda: get_driver().session(database=DB)
    started=time.perf_counter()
    with patch.object(verifier,'get_session',session):
        result=verifier.verify_intent(**arguments(spec))
    return result, round((time.perf_counter()-started)*1000,3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    snapshot=json.loads(args.snapshot.read_bytes())
    specs=fixture_specs(snapshot)
    previous=json.loads((OUT/'controlled_D_E.json').read_bytes()) if (OUT/'controlled_D_E.json').exists() else None
    if previous and previous['metadata'].get('completed'):
        raise RuntimeError('Completed results already exist; preserve them and use a separate run directory')
    references={'created_at_utc':datetime.now(timezone.utc).isoformat(),'review_status':'assistant_authored_controlled_fixtures_pending_researcher_review',
        'snapshot_source':str(args.snapshot),'snapshot_sha256':hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),'database':DB,'fixtures':specs,
        'D_expected':{'control':'APPROVED',**{m:'REJECTED' for m in MUTATIONS}},
        'E_expected':{'fresh_complete':'APPROVED','stale':'INSUFFICIENT_EVIDENCE','incomplete_missing_path':'INSUFFICIENT_EVIDENCE','deactivated_membership':'REJECTED','failed_refresh_fresh_snapshot_retained':'APPROVED','database_unavailable':'INSUFFICIENT_EVIDENCE'},
        'notes':['Only one resource/path exists per fixture, preventing alternative-path masking.','All node identities and properties are preserved by each D mutation.','Lifecycle acquisition and database outages are injected, not real network outages.','Failed refresh retains a fresh, complete previously accepted snapshot; approval is expected under the current retention policy.']}
    if previous:
        references=json.loads((OUT/'controlled_references.json').read_bytes())
        assert references['fixtures']==specs
    else:
        save('controlled_references.json',references)
    before=live_fingerprint()
    ensure_fixture_database()
    report={'metadata':{'started_at_utc':datetime.now(timezone.utc).isoformat(),'database':DB,'live_database':'neo4j','live_before':before,
        'production_verifier_sha256':hashlib.sha256((ROOT/'source/db/verifier.py').read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reference_review':references['review_status'],'LLM_calls':0,'transaction_broadcast':False,'concurrency':1,'freshness_hours':settings.knowledge_max_age_hours,
        'database_unavailable_injected':True,'source_failure_injected':True},'D':[],'E':[]}
    if previous:
        report=previous
        assert report['metadata']['live_before']==before, 'Live graph changed since initial fixture run'
        report['metadata'].setdefault('continuations',[]).append({'timestamp_utc':datetime.now(timezone.utc).isoformat(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'retained_D':len(report['D']),'retained_E':len(report['E'])})
    done_d={r['id'] for r in report['D']}
    done_e={(r['id'],r['repeat']) for r in report['E']}
    logging.disable(logging.CRITICAL)
    try:
        for spec in specs:
            for mutation in ['control',*MUTATIONS]:
                if f"{spec['id']}:{mutation}" in done_d: continue
                fixture=materialize(spec); initial=state(); changed=None
                if mutation!='control': changed=delete_edge(spec,mutation)
                modified=state()
                assert initial['nodes']==modified['nodes']
                assert len(initial['edges'])-len(modified['edges'])==(mutation!='control')
                actual,latency=verify(spec)
                baseline=entity_baseline(spec)
                expected=references['D_expected'][mutation]
                report['D'].append({'id':f"{spec['id']}:{mutation}",'fixture_id':spec['id'],'mutation':mutation,'input':arguments(spec),
                    'expected':expected,'actual':actual,'baseline':baseline,'wall_latency_ms':latency,'mutation_detail':changed,
                    'entities_preserved':True,'node_count':len(modified['nodes']),'edge_count':len(modified['edges']),
                    'initial_state_sha256':digest(initial),'modified_state_sha256':digest(modified),
                    'fixture_definition':fixture,'passes':actual['decision']==expected})
                save('controlled_D_E.json',report);clear_fixture()
            print(f"D: {spec['id']} control and five mutations complete",flush=True)
        for spec in [specs[0],next(s for s in specs if s['action']=='supply')]:
            for condition,expected in references['E_expected'].items():
                for repeat in range(1,4):
                    if (f"{spec['protocol_key']}:{condition}",repeat) in done_e: continue
                    materialize(spec); initial=state(); sync_result=None
                    if condition=='stale':
                        old=(datetime.now(timezone.utc)-timedelta(hours=settings.knowledge_max_age_hours+1)).isoformat()
                        query("MATCH (d:ProtocolDeployment) SET d.last_successful_sync_at=$stamp",stamp=old)
                    elif condition=='incomplete_missing_path':
                        query("MATCH (d:ProtocolDeployment) SET d.pool_discovery_complete=false,d.asset_coverage='partial'")
                        delete_edge(spec,'resource_asset')
                    elif condition=='deactivated_membership':
                        query("MATCH (:ProtocolDeployment)-[r:HAS_POOL|HAS_RESERVE]->() SET r.active=false")
                    elif condition=='failed_refresh_fresh_snapshot_retained':
                        def fail_acquire(): raise TimeoutError('Controlled source acquisition failure')
                        task=sync.SyncTask('fixture-source',f"{spec['protocol_key']}:11155111",'fixture:controlled-acquisition',fail_acquire,lambda x:None,lambda x:(_ for _ in ()).throw(AssertionError('Admission must not run')))
                        with patch.object(sync,'get_session',lambda:get_driver().session(database=DB)):
                            sync_result=asdict(sync.run_task(task))
                        query("MATCH (s:KnowledgeSource {key:'fixture-source',url:'fixture:controlled-acquisition'}) SET s._eval_owner=$owner,s._eval_id='source'",owner=OWNER)
                    actual,latency=verify(spec,condition=='database_unavailable')
                    report['E'].append({'id':f"{spec['protocol_key']}:{condition}",'condition':condition,'repeat':repeat,'input':arguments(spec),
                        'expected':expected,'actual':actual,'wall_latency_ms':latency,'sync_result':sync_result,
                        'knowledge_state':query("MATCH (d:ProtocolDeployment) RETURN properties(d) AS properties"),
                        'initial_state_sha256':digest(initial),'evaluated_state_sha256':digest(state()),'passes':actual['decision']==expected,
                        'operational_failure':condition=='database_unavailable','outage_injected':condition=='database_unavailable'})
                    save('controlled_D_E.json',report);clear_fixture()
            print(f"E: {spec['protocol']} six states x three repeats complete",flush=True)
    finally:
        clear_fixture()
        report['metadata']['fixture_nodes_after_cleanup']=query('MATCH (n) RETURN count(n) AS count')[0]['count']
        report['metadata']['live_after']=live_fingerprint()
        report['metadata']['live_unchanged']=before==report['metadata']['live_after']
        report['metadata']['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        report['metadata']['completed']=len(report['D'])==72 and len(report['E'])==36
        save('controlled_D_E.json',report);close_driver();logging.disable(logging.NOTSET)
    print(json.dumps({'D':len(report['D']),'D_matches':sum(r['passes'] for r in report['D']),'E':len(report['E']),'E_matches':sum(r['passes'] for r in report['E']),'live_unchanged':report['metadata']['live_unchanged']}))


if __name__=='__main__':
    main()
