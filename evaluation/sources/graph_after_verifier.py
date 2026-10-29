"""Relationship-path verification against admitted local Neo4j knowledge."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from core.config import settings
from core.models import Decision
from db.connection import get_session
from db.verification_trace import diagnose_path, failure, knowledge_context, trace


logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOLS = {"uniswap v3": "Uniswap V3", "aave v3": "Aave V3"}
LENDING_ACTIONS = {"supply", "withdraw", "borrow", "repay"}

KNOWLEDGE_STATE = """
MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
      (deployment:ProtocolDeployment {chain_id:$chain_id})
WHERE toLower(family.name)=toLower($protocol)
RETURN deployment.key AS key,
       deployment.last_successful_sync_at AS last_successful_sync_at,
       deployment.last_synced_at AS last_synced_at,
       deployment.last_sync_status AS last_sync_status,
       deployment.asset_coverage AS asset_coverage,
       deployment.pool_discovery_complete AS pool_discovery_complete,
       deployment.source_url AS source_url
LIMIT 1
"""

CYPHER_SWAP = """
MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
      (deployment:ProtocolDeployment {verified:true, chain_id:$chain_id})
WHERE toLower(family.name) = toLower($protocol)
MATCH (deployment)-[:SUPPORTS_ACTION]->(action:Action {name:'swap'})
MATCH (deployment)-[pool_rel:HAS_POOL]->
      (pool:Pool {verified:true, verification_eligible:true, active:true, chain_id:$chain_id})
MATCH (pool)-[:SUPPORTS_TOKEN]->
      (t1:Token {symbol:$token_in, verified:true, verification_eligible:true, chain_id:$chain_id})
MATCH (pool)-[:SUPPORTS_TOKEN]->
      (t2:Token {symbol:$token_out, verified:true, verification_eligible:true, chain_id:$chain_id})
MATCH (deployment)-[router_rel:DEPLOYED_CONTRACT {role:'swap_router'}]->
      (router:Contract {verified:true})-[:EXPOSES_FUNCTION]->
      (fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->(action)
MATCH (deployment)-[quoter_rel:DEPLOYED_CONTRACT {role:'quoter'}]->
      (quoter:Contract {verified:true})-[:EXPOSES_FUNCTION]->
      (:Function {verified:true, purpose:'preflight'})-[:IMPLEMENTS_ACTION]->(action)
WHERE pool_rel.active=true AND router_rel.active=true AND quoter_rel.active=true
  AND t1.address <> t2.address
  AND t1.decimals IS NOT NULL AND t2.decimals IS NOT NULL AND pool.fee IS NOT NULL
RETURN router.address AS address, quoter.address AS quoter_address,
       pool.address AS pool_address, pool.fee AS pool_fee,
       coalesce(pool.featured, false) AS featured,
       t1.address AS token_in_address, t1.symbol AS token_in_symbol,
       t1.decimals AS token_in_decimals,
       t2.address AS token_out_address, t2.symbol AS token_out_symbol,
       t2.decimals AS token_out_decimals,
       fn.name AS function_name, fn.signature AS function_signature,
       fn.selector AS function_selector,
       family.name AS protocol, $chain_id AS chain_id
ORDER BY featured DESC, pool.fee ASC, pool.address ASC
LIMIT 20
"""

CYPHER_LENDING = """
MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
      (deployment:ProtocolDeployment {verified:true, chain_id:$chain_id})
WHERE toLower(family.name) = toLower($protocol)
MATCH (deployment)-[:SUPPORTS_ACTION]->(action:Action {name:$action})
MATCH (deployment)-[reserve_rel:HAS_RESERVE]->
      (reserve:Reserve {verified:true, active:true})
MATCH (reserve)-[:UNDERLYING_ASSET]->
      (token:Token {symbol:$token_in, chain_id:$chain_id, verified:true})
MATCH (reserve)-[:SUPPORTS_ACTION]->(action)
MATCH (deployment)-[pool_rel:DEPLOYED_CONTRACT {role:'pool'}]->
      (pool:Contract {verified:true})-[:EXPOSES_FUNCTION]->
      (fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->(action)
WHERE reserve_rel.active=true AND pool_rel.active=true
RETURN pool.address AS address, null AS pool_address,
       token.address AS token_address, token.decimals AS token_decimals,
       fn.name AS function_name, fn.signature AS function_signature,
       fn.selector AS function_selector,
       family.name AS protocol, $chain_id AS chain_id
LIMIT 1
"""


def _elapsed(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _network_name(chain_id: int) -> str:
    if chain_id == 1:
        return "Ethereum Mainnet"
    if chain_id == 11155111:
        return "Ethereum Sepolia"
    return f"Chain {chain_id}"


def _result(decision: Decision, reason: str, protocol, action, chain_id, start, **extra):
    explanation = extra.pop("trace", None)
    if explanation is None:
        explanation = trace(
            extra.pop("rule_id"),
            extra.pop("knowledge", knowledge_context(max_age_hours=settings.knowledge_max_age_hours)),
            extra.pop("failures", ()),
        )
    return {
        "decision": decision.value,
        "verified_address": None,
        "reason": reason,
        "protocol": protocol,
        "action": action,
        "chain_id": chain_id,
        "network": _network_name(chain_id),
        "rule_id": explanation["rule_id"],
        "trace": explanation,
        "knowledge": explanation["knowledge"],
        "latency_ms": _elapsed(start),
        **extra,
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _freshness(state: dict) -> tuple[bool, str]:
    timestamp = _parse_timestamp(
        state.get("last_successful_sync_at") or state.get("last_synced_at")
    )
    if not timestamp:
        return False, "Knowledge has no recorded successful synchronization timestamp."
    age_hours = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
    if age_hours > settings.knowledge_max_age_hours:
        return False, (
            f"Knowledge is stale ({age_hours:.1f} hours old; maximum is "
            f"{settings.knowledge_max_age_hours} hours)."
        )
    return True, "Knowledge freshness is within the configured limit."


def verify_intent(protocol, token_in, token_out=None, action="swap", chain_id=11155111):
    """Verify an action-specific relationship path in fresh admitted knowledge."""
    start = time.perf_counter()
    normalized_protocol = SUPPORTED_PROTOCOLS.get(str(protocol or "").strip().lower())
    action = str(action or "").strip().lower()
    token_in = str(token_in or "").strip().upper()
    token_out = str(token_out or "").strip().upper() or None

    if chain_id != settings.supported_chain_id:
        return _result(Decision.UNSUPPORTED, f"Unsupported chain ID: {chain_id}", protocol, action, chain_id, start,
                       rule_id="SCOPE.CHAIN", failures=[failure("SCOPE.CHAIN", {"field":"chain_id"},
                           {"value":settings.supported_chain_id}, {"value":chain_id}, "configured_scope")])
    if not normalized_protocol:
        return _result(Decision.UNSUPPORTED, f"Unsupported protocol: {protocol}", protocol, action, chain_id, start,
                       rule_id="SCOPE.PROTOCOL", failures=[failure("SCOPE.PROTOCOL", {"field":"protocol"},
                           {"allowed":list(SUPPORTED_PROTOCOLS.values())}, {"value":protocol}, "configured_scope")])
    if action == "swap" and normalized_protocol != "Uniswap V3":
        return _result(Decision.UNSUPPORTED, "Swap verification is supported only for Uniswap V3.", normalized_protocol, action, chain_id, start,
                       rule_id="SCOPE.ACTION_PROTOCOL", failures=[failure("SCOPE.ACTION_PROTOCOL", {"action":action},
                           {"protocol":"Uniswap V3"}, {"protocol":normalized_protocol}, "configured_scope")])
    if action in LENDING_ACTIONS and normalized_protocol != "Aave V3":
        return _result(Decision.UNSUPPORTED, f"{action.title()} verification is supported only for Aave V3.", normalized_protocol, action, chain_id, start,
                       rule_id="SCOPE.ACTION_PROTOCOL", failures=[failure("SCOPE.ACTION_PROTOCOL", {"action":action},
                           {"protocol":"Aave V3"}, {"protocol":normalized_protocol}, "configured_scope")])
    if action not in {"swap", *LENDING_ACTIONS}:
        return _result(Decision.UNSUPPORTED, f"Unsupported action: {action}", normalized_protocol, action, chain_id, start,
                       rule_id="SCOPE.ACTION", failures=[failure("SCOPE.ACTION", {"field":"action"},
                           {"allowed":["swap"] if normalized_protocol == "Uniswap V3" else sorted(LENDING_ACTIONS)},
                           {"value":action}, "configured_scope")])
    if not token_in or (action == "swap" and not token_out):
        return _result(Decision.REJECTED, "The structured intent is missing required asset fields.", normalized_protocol, action, chain_id, start,
                       rule_id="INPUT.REQUIRED_ASSET", failures=[failure("INPUT.REQUIRED_ASSET", {"field":field},
                           {"nonempty":True}, {"value":value}, "structured_graph_input")
                           for field,value in [("token_in",token_in)] + ([("token_out",token_out)] if action == "swap" else []) if not value])

    try:
        with get_session() as session:
            state_record = session.run(
                KNOWLEDGE_STATE, protocol=normalized_protocol, chain_id=chain_id
            ).single()
            if not state_record:
                return _result(
                    Decision.INSUFFICIENT_EVIDENCE,
                    "The supported deployment has not been synchronized into local knowledge.",
                    normalized_protocol, action, chain_id, start,
                    rule_id="KNOWLEDGE.DEPLOYMENT_UNAVAILABLE",
                    failures=[failure("KNOWLEDGE.DEPLOYMENT_UNAVAILABLE",
                        {"protocol":normalized_protocol,"chain_id":chain_id},
                        {"deployment_context_present":True}, {"deployment_context_present":False})],
                )
            state = dict(state_record)
            fresh, freshness_reason = _freshness(state)
            complete = state.get("pool_discovery_complete") is True if action == "swap" else state.get("asset_coverage") == "official-address-book-complete"
            knowledge = knowledge_context(state, fresh=fresh, complete=complete,
                                          max_age_hours=settings.knowledge_max_age_hours)
            if not fresh:
                timestamp = _parse_timestamp(state.get("last_successful_sync_at") or state.get("last_synced_at"))
                freshness_rule = "KNOWLEDGE.STALE" if timestamp else "KNOWLEDGE.TIMESTAMP_UNAVAILABLE"
                return _result(
                    Decision.INSUFFICIENT_EVIDENCE, freshness_reason,
                    normalized_protocol, action, chain_id, start,
                    knowledge=knowledge, rule_id=freshness_rule,
                    failures=[failure(freshness_rule, {"deployment_key":state.get("key")},
                        {"valid_sync_timestamp":True,"max_age_hours":settings.knowledge_max_age_hours},
                        {"timestamp":state.get("last_successful_sync_at") or state.get("last_synced_at"),
                         "age_hours":(datetime.now(timezone.utc)-timestamp).total_seconds()/3600 if timestamp else None})],
                )

            if action == "swap":
                records = list(session.run(
                    CYPHER_SWAP,
                    protocol=normalized_protocol,
                    token_in=token_in,
                    token_out=token_out,
                    chain_id=chain_id,
                ))
                if records:
                    routes = [{
                        "router_address": record["address"],
                        "quoter_address": record["quoter_address"],
                        "pool_address": record["pool_address"],
                        "pool_fee": record["pool_fee"],
                        "token_in_address": record["token_in_address"],
                        "token_in_symbol": record["token_in_symbol"],
                        "token_in_decimals": record["token_in_decimals"],
                        "token_out_address": record["token_out_address"],
                        "token_out_symbol": record["token_out_symbol"],
                        "token_out_decimals": record["token_out_decimals"],
                        "function_name": record["function_name"],
                        "function_signature": record["function_signature"],
                        "function_selector": record["function_selector"],
                    } for record in records]
                    first = records[0]
                    return {
                        "decision": Decision.APPROVED.value,
                        "verified_address": first["address"],
                        "verified_pool": first["pool_address"],
                        "verified_function": first["function_signature"],
                        "verified_selector": first["function_selector"],
                        "protocol": first["protocol"],
                        "action": action,
                        "chain_id": first["chain_id"],
                        "network": _network_name(chain_id),
                        "routes": routes,
                        "knowledge": {"fresh": True, "complete": state.get("pool_discovery_complete")},
                        "latency_ms": _elapsed(start),
                    }
                complete = state.get("pool_discovery_complete") is True
            else:
                record = session.run(
                    CYPHER_LENDING,
                    protocol=normalized_protocol,
                    token_in=token_in,
                    action=action,
                    chain_id=chain_id,
                ).single()
                if record:
                    return {
                        "decision": Decision.APPROVED.value,
                        "verified_address": record["address"],
                        "verified_pool": record["pool_address"],
                        "verified_asset": record["token_address"],
                        "verified_asset_decimals": record["token_decimals"],
                        "verified_function": record["function_signature"],
                        "verified_selector": record["function_selector"],
                        "protocol": record["protocol"],
                        "action": action,
                        "chain_id": record["chain_id"],
                        "network": _network_name(chain_id),
                        "knowledge": {"fresh": True, "complete": True},
                        "latency_ms": _elapsed(start),
                    }
                complete = state.get("asset_coverage") == "official-address-book-complete"

            decision = Decision.REJECTED if complete else Decision.INSUFFICIENT_EVIDENCE
            if complete:
                reason = f"No authoritative relationship path exists for {normalized_protocol} / {action} / {token_in}"
                if token_out:
                    reason += f" -> {token_out}"
            else:
                reason = "The requested relationship was not found, but synchronized knowledge is incomplete."
            try:
                explanation = diagnose_path(session, CYPHER_SWAP if action == "swap" else CYPHER_LENDING,
                    {"protocol":normalized_protocol,"action":action,"token_in":token_in,
                     "token_out":token_out,"chain_id":chain_id}, knowledge)
            except Exception as exc:
                explanation = trace("GRAPH.PATH.NOT_FOUND_COMPLETE" if complete else "GRAPH.PATH.NOT_FOUND_INCOMPLETE",
                    knowledge, status="unavailable", error_code=type(exc).__name__, limitations=[
                        "Diagnostics unavailable; the original decision is retained without a specific failure assertion."])
            return _result(
                decision, reason, normalized_protocol, action, chain_id, start,
                trace=explanation,
            )
    except Exception:
        logger.exception("Graph verification failed")
        return _result(
            Decision.INSUFFICIENT_EVIDENCE,
            "Authoritative graph knowledge is temporarily unavailable.",
            normalized_protocol, action, chain_id, start,
            trace=trace("KNOWLEDGE.UNAVAILABLE", knowledge_context(max_age_hours=settings.knowledge_max_age_hours),
                [failure("KNOWLEDGE.UNAVAILABLE", {"service":"graph_verification"},
                         {"knowledge_read_success":True}, {"knowledge_read_success":False,"specific_cause":None},
                         "runtime_observation")], status="unavailable"),
        )


if __name__ == "__main__":
    import json
    print(json.dumps(verify_intent("Uniswap V3", "USDC", "WETH", "swap"), indent=2))
