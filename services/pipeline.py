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
            if contextual.intent:
                merged_data = pending.intent.model_dump()
                contextual_data = contextual.intent.model_dump()
                for field in pending.missing_fields:
                    if contextual_data.get(field) is not None:
                        merged_data[field] = contextual_data[field]
                if any(
                    contextual_data.get(field) is not None
                    for field in pending.missing_fields
                ):
                    merged = type(pending.intent).model_validate(merged_data)
            if merged:
                resolution = validate_candidate(merged)
            elif contextual.status in {Decision.UNSUPPORTED, Decision.REJECTED}:
                resolution = contextual
            else:
                resolution = validate_candidate(pending.intent)
                resolution.message = (
                    "That message did not answer the pending clarification. "
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
            "conversation_id": conversation_id,
            "executable": False,
        }

    intent = resolution.intent
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
        )
        graph_result["verification_id"] = capability_store.issue(operation)
        graph_result["verification_expires_in"] = settings.verification_ttl_seconds
        graph_result["executable"] = True
    return graph_result
