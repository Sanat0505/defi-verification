"""Natural language -> intent -> graph verification orchestration."""

from __future__ import annotations

import asyncio
import logging
import uuid

from core.config import settings
from core.models import ApprovedOperation, Decision, PromptRequest
from core.state import capability_store, conversation_store
from db.verifier import verify_intent
from llm.intent_parser import parse_clarification, parse_intent
from llm.normalization import merge_clarification, validate_candidate


logger = logging.getLogger(__name__)


async def process_prompt(request: PromptRequest) -> dict:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    if request.new_operation:
        conversation_store.clear(conversation_id)

    pending = conversation_store.get(conversation_id)
    resolution = await parse_intent(request.prompt)

    if pending and resolution.status == Decision.NEEDS_CLARIFICATION and resolution.intent:
        update = resolution.intent
        if not update.action and not update.protocol and (
            update.slippage_bps is not None and update.slippage_bps != pending.intent.slippage_bps
        ):
            return {
                "decision": "NEEDS_CLARIFICATION", "executable": False,
                "message": "To add or change slippage, submit the complete operation with that limit. The pending operation has not been executed.",
                "error_code": "clarification_changes_constraints",
                "conversation_id": conversation_id,
                "intent": pending.intent.model_dump(mode="json", exclude_none=True),
                "missing_fields": pending.missing_fields,
            }
        merged = merge_clarification(
            pending.intent, pending.missing_fields, resolution.intent
        )
        if merged:
            resolution = validate_candidate(merged)
        elif not resolution.intent.action and not resolution.intent.protocol:
            contextual = await parse_clarification(
                request.prompt,
                pending.intent.model_dump(mode="json", exclude_none=True),
                pending.missing_fields,
            )
            if contextual.status in {Decision.UNSUPPORTED, Decision.REJECTED, Decision.ERROR}:
                resolution = contextual
            else:
                if contextual.intent:
                    merged = merge_clarification(pending.intent, pending.missing_fields, contextual.intent)
                if merged:
                    resolution = validate_candidate(merged)
                else:
                    resolution = validate_candidate(pending.intent)
                    resolution.message = (
                        "That answer did not safely fill the missing fields. Resubmit the full operation to change any conditions. "
                        + resolution.message
                    )

    if resolution.status == Decision.NEEDS_CLARIFICATION and resolution.intent:
        conversation_store.put(
            conversation_id, resolution.intent, resolution.missing_fields
        )
    elif resolution.status != Decision.ERROR:
        conversation_store.clear(conversation_id)

    if resolution.status != Decision.APPROVED or not resolution.intent:
        return {
            "decision": resolution.status.value,
            "message": resolution.message,
            "missing_fields": resolution.missing_fields,
            "intent": (
                resolution.intent.model_dump(mode="json", exclude_none=True)
                if resolution.intent else None
            ),
            "error_code": resolution.error_code,
            "unhandled_constraints": resolution.unhandled_constraints,
            "conversation_id": conversation_id,
            "executable": False,
        }

    intent = resolution.intent
    # Recheck the candidate before issuing an execution capability.
    validation = validate_candidate(intent)
    if validation.status != Decision.APPROVED:
        return {
            "decision": validation.status.value, "message": validation.message,
            "error_code": validation.error_code, "executable": False,
            "conversation_id": conversation_id, "unhandled_constraints": validation.unhandled_constraints,
        }
    slippage_bps, slippage_source = None, None
    if intent.action == "swap":
        slippage_bps = intent.slippage_bps if intent.slippage_bps is not None else settings.swap_slippage_bps
        slippage_source = "user" if intent.slippage_bps is not None else "configured_default"
        if type(slippage_bps) is not int or not 1 <= slippage_bps <= 500:
            return {"decision": "ERROR", "executable": False, "error_code": "invalid_slippage_configuration",
                    "message": "The configured swap slippage must be between 1 and 500 basis points.",
                    "conversation_id": conversation_id}
    logger.info(
        "Verifying normalized intent action=%s protocol=%s chain_id=%s",
        intent.action, intent.protocol, intent.chain_id,
    )
    graph_result = await asyncio.to_thread(
        verify_intent,
        intent.protocol,
        intent.token_in,
        intent.token_out,
        intent.action,
        intent.chain_id,
    )
    graph_result["intent"] = intent.model_dump(mode="json", exclude_none=True)
    graph_result["conversation_id"] = conversation_id
    graph_result["executable"] = False

    if graph_result["decision"] == Decision.APPROVED.value:
        operation = ApprovedOperation(
            intent=intent,
            protocol=graph_result["protocol"],
            action=graph_result["action"],
            chain_id=graph_result["chain_id"],
            network=graph_result["network"],
            verified_address=graph_result["verified_address"],
            verified_pool=graph_result.get("verified_pool"),
            verified_asset=graph_result.get("verified_asset"),
            verified_asset_symbol=intent.token_in,
            verified_asset_decimals=graph_result.get("verified_asset_decimals"),
            verified_function=graph_result["verified_function"],
            verified_selector=graph_result["verified_selector"],
            routes=graph_result.get("routes") or [],
            interest_rate_mode=(2 if intent.action in {"borrow", "repay"} else None),
            slippage_bps=slippage_bps,
            slippage_source=slippage_source,
        )
        graph_result["verification_id"] = capability_store.issue(operation)
        graph_result["verification_expires_in"] = settings.verification_ttl_seconds
        graph_result["executable"] = True
        if slippage_bps is not None:
            graph_result["execution_parameters"] = {"slippage_bps": slippage_bps, "slippage_source": slippage_source}
    return graph_result
