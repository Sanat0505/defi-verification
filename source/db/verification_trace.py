"""Read-only failure witnesses for a decision already made by the verifier.

Relationship witnesses relax exactly one edge requirement of the original path
query. Every remaining path predicate must still hold. They describe candidate
paths in the local database, not protocol truth or a unique global root cause.
"""
from functools import lru_cache

from neo4j import Query

from source.core.models import VerificationFailure, VerificationTrace


def failure(rule_id, subject, expected, observed, scope="admitted_local_snapshot"):
    return VerificationFailure(rule_id=rule_id, subject=subject, expected=expected,
                               observed=observed, evidence_scope=scope).model_dump(mode="json")


def trace(rule_id, knowledge, failures=(), status="observed", limitations=(), error_code=None):
    return VerificationTrace(rule_id=rule_id, failures=list(failures),
                             diagnostic_status=status, knowledge=knowledge,
                             limitations=list(limitations), diagnostic_error_code=error_code).model_dump(mode="json")


def knowledge_context(state=None, *, fresh=None, complete=None, max_age_hours=None):
    state = state or {}
    return {
        "scope": "admitted_local_snapshot",
        "deployment_key": state.get("key"),
        "source_url": state.get("source_url"),
        "last_successful_sync_at": state.get("last_successful_sync_at"),
        "last_synced_at": state.get("last_synced_at"),
        "last_sync_status": state.get("last_sync_status"),
        "asset_coverage": state.get("asset_coverage"),
        "pool_discovery_complete": state.get("pool_discovery_complete"),
        "fresh": fresh,
        "complete": complete,
        "max_age_hours": max_age_hours,
        "absence_interpretation": (
            "confirmed_under_declared_local_coverage" if fresh and complete
            else "insufficient_to_establish_protocol_absence"
        ),
    }


def _identity(var):
    # Explicit public graph identifiers only; no arbitrary properties or fixture IDs.
    return (f"{{element_id:elementId({var}), labels:labels({var}), key:{var}.key, "
            f"address:{var}.address, symbol:{var}.symbol, name:{var}.name, "
            f"signature:{var}.signature, selector:{var}.selector, chain_id:{var}.chain_id}}")


@lru_cache(maxsize=2)
def relationship_queries(base_query, swap):
    """Build bounded witnesses from the exact approval query, never a second policy."""
    head = base_query.split("RETURN", 1)[0].lstrip()
    if swap:
        head = head.replace("(:Function {verified:true, purpose:'preflight'})", "(qfn:Function {verified:true, purpose:'preflight'})")
        edges = [
            ("(deployment)-[:SUPPORTS_ACTION]->", "(deployment), ", "deployment", "action", "SUPPORTS_ACTION", None, None),
            ("(deployment)-[pool_rel:HAS_POOL]->", "(deployment), ", "deployment", "pool", "HAS_POOL", "pool_rel", None),
            ("(pool)-[:SUPPORTS_TOKEN]->\n      (t1", "(pool),\n      (t1", "pool", "t1", "SUPPORTS_TOKEN", None, None),
            ("(pool)-[:SUPPORTS_TOKEN]->\n      (t2", "(pool),\n      (t2", "pool", "t2", "SUPPORTS_TOKEN", None, None),
            ("(deployment)-[router_rel:DEPLOYED_CONTRACT {role:'swap_router'}]->", "(deployment), ", "deployment", "router", "DEPLOYED_CONTRACT", "router_rel", "swap_router"),
            ("(router:Contract {verified:true})-[:EXPOSES_FUNCTION]->", "(router:Contract {verified:true}), ", "router", "fn", "EXPOSES_FUNCTION", None, None),
            ("(fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->", "(fn:Function {verified:true, purpose:'execute'}), ", "fn", "action", "IMPLEMENTS_ACTION", None, None),
            ("(deployment)-[quoter_rel:DEPLOYED_CONTRACT {role:'quoter'}]->", "(deployment), ", "deployment", "quoter", "DEPLOYED_CONTRACT", "quoter_rel", "quoter"),
            ("(quoter:Contract {verified:true})-[:EXPOSES_FUNCTION]->", "(quoter:Contract {verified:true}), ", "quoter", "qfn", "EXPOSES_FUNCTION", None, None),
            ("(qfn:Function {verified:true, purpose:'preflight'})-[:IMPLEMENTS_ACTION]->", "(qfn:Function {verified:true, purpose:'preflight'}), ", "qfn", "action", "IMPLEMENTS_ACTION", None, None),
        ]
    else:
        edges = [
            ("(deployment)-[:SUPPORTS_ACTION]->", "(deployment), ", "deployment", "action", "SUPPORTS_ACTION", None, None),
            ("(deployment)-[reserve_rel:HAS_RESERVE]->", "(deployment), ", "deployment", "reserve", "HAS_RESERVE", "reserve_rel", None),
            ("(reserve)-[:UNDERLYING_ASSET]->", "(reserve), ", "reserve", "token", "UNDERLYING_ASSET", None, None),
            ("(reserve)-[:SUPPORTS_ACTION]->", "(reserve), ", "reserve", "action", "SUPPORTS_ACTION", None, None),
            ("(deployment)-[pool_rel:DEPLOYED_CONTRACT {role:'pool'}]->", "(deployment), ", "deployment", "pool", "DEPLOYED_CONTRACT", "pool_rel", "pool"),
            ("(pool:Contract {verified:true})-[:EXPOSES_FUNCTION]->", "(pool:Contract {verified:true}), ", "pool", "fn", "EXPOSES_FUNCTION", None, None),
            ("(fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->", "(fn:Function {verified:true, purpose:'execute'}), ", "fn", "action", "IMPLEMENTS_ACTION", None, None),
        ]
    branches = []
    for old,new,left,right,kind,active_var,role in edges:
        if head.count(old) != 1:
            raise ValueError("Approval query changed; diagnostic pattern requires review")
        relaxed = head.replace(old,new,1)
        if active_var:
            relaxed = relaxed.replace(active_var + ".active=true", "true")
        # DISTINCT is a real planning boundary; plain WITH can be inlined. Removing
        # duplicate bindings preserves witness existence and all original predicates.
        relaxed = relaxed.replace("\nMATCH ", "\nWITH DISTINCT *\nMATCH ")
        # No relationship filters here: observe inactive edges and incorrect roles too.
        optional = f"OPTIONAL MATCH ({left})-[observed_rel:{kind}]->({right})\n"
        attrs = ("{active:true" + (f", role:'{role}'" if role else "") + "}") if active_var else "{}"
        invalid = "observed_rel IS NULL"
        if active_var:
            invalid += " OR NOT coalesce(observed_rel.active=true,false)"
        if role:
            invalid += f" OR coalesce(observed_rel.role <> '{role}',true)"
        valid = []
        if active_var:
            valid.append("qualifying_rel.active=true")
        if role:
            valid.append(f"qualifying_rel.role='{role}'")
        qualifying = f"EXISTS {{ MATCH ({left})-[qualifying_rel:{kind}]->({right})" + (" WHERE " + " AND ".join(valid) if valid else "") + " }"
        branches.append("CALL {\n" + relaxed + optional +
            f"WITH *, observed_rel IS NOT NULL AS present WHERE ({invalid}) AND NOT {qualifying}\n" +
            f"RETURN '{kind}' AS relationship, {_identity(left)} AS source, {_identity(right)} AS target, " +
            f"{attrs} AS expected_properties, present, " +
            "CASE WHEN observed_rel IS NULL THEN {} ELSE {active:observed_rel.active, role:observed_rel.role} END AS observed_properties\nLIMIT 5\n}\n" +
            "RETURN relationship, source, target, expected_properties, present, observed_properties")
    return tuple(branches)


TOKEN_OBSERVATIONS = """
UNWIND $symbols AS symbol
OPTIONAL MATCH (token:Token {symbol:symbol, chain_id:$chain_id})
RETURN symbol, collect(token {address:token.address, verified:token.verified,
       verification_eligible:token.verification_eligible, decimals:token.decimals}) AS candidates
"""


def diagnose_path(session, base_query, params, knowledge):
    """Diagnostic failure/timeout cannot replace the already selected decision."""
    rule = "GRAPH.PATH.NOT_FOUND_COMPLETE" if knowledge["complete"] else "GRAPH.PATH.NOT_FOUND_INCOMPLETE"
    limitations = [
        "Observations describe admitted local knowledge, not independent protocol truth.",
        "At most five candidate witnesses from the first localized edge check are returned; this is not an exhaustive or unique root-cause proof.",
        "Diagnostic reads follow the decision query; concurrent graph changes can limit localization.",
    ]
    try:
        symbols = list(dict.fromkeys(t for t in (params["token_in"], params.get("token_out")) if t))
        rows = list(session.run(Query(TOKEN_OBSERVATIONS, timeout=2.0), symbols=symbols, chain_id=params["chain_id"]))
        failures = []
        for row in rows:
            if not row["candidates"]:
                failures.append(failure("GRAPH.ENTITY.TOKEN_NOT_FOUND",
                    {"label":"Token", "symbol":row["symbol"], "chain_id":params["chain_id"]},
                    {"present":True}, {"present":False, "matching_nodes":0}))
        if failures:
            return trace(rule,knowledge,failures,limitations=limitations)
        for query in relationship_queries(base_query, params["action"] == "swap"):
            witnesses = list(session.run(Query(query, timeout=2.0), **params))
            for row in witnesses:
                failures.append(failure("GRAPH.RELATIONSHIP." + row["relationship"],
                    {"relationship":row["relationship"], "source":dict(row["source"]), "target":dict(row["target"])},
                    {"present":True, "properties":dict(row["expected_properties"])},
                    {"present":bool(row["present"]), "properties":dict(row["observed_properties"])}))
            if failures:
                return trace(rule,knowledge,failures,limitations=limitations)
        return trace(rule,knowledge,[failure("GRAPH.PATH.NO_QUALIFYING_PATH",
            {"protocol":params["protocol"], "action":params["action"], "token_in":params["token_in"],
             "token_out":params.get("token_out"), "chain_id":params["chain_id"]},
            {"qualifying_path_present":True}, {"qualifying_path_present":False, "specific_cause":None})],
            status="not_localized", limitations=limitations + ["No single-edge witness was established; node properties, metadata or multiple failures may be involved."])
    except Exception as exc:
        # Do not export database/transport exception strings or change disposition.
        return trace(rule,knowledge,status="unavailable",error_code=getattr(exc,"code",type(exc).__name__),limitations=limitations + [
            "Additional diagnostics failed or timed out; no specific failed entity or edge is asserted."])
