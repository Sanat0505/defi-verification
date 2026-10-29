"""HTTP endpoints for intent verification and approved-operation submission."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import settings
from core.models import Decision, ExecuteRequest, PromptRequest
from core.state import capability_store, conversation_store
from db.connection import check_connection, close_driver
from db.verifier import verify_intent
from services.pipeline import process_prompt
from llm.normalization import validate_candidate
from wallet.erc4337 import add_to_whitelist, execute_aave, execute_swap
from api.knowledge import router as knowledge_router


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        logger.info("Waiting for Neo4j to accept database queries")
        try:
            await asyncio.to_thread(check_connection)
        except Exception as exc:
            raise RuntimeError(
                "Neo4j is not ready. Wait for the instance to finish starting, "
                "check NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD, then run "
                "'python -m db.connection' before restarting the API."
            ) from exc
        logger.info("Neo4j is ready")
        yield
    finally:
        close_driver()


app = FastAPI(
    title="DeFi Relationship Verification Prototype",
    lifespan=lifespan,
)
app.include_router(knowledge_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/verify")
async def verify(request: PromptRequest):
    logger.info("Verification request received conversation_id=%s", request.conversation_id)
    return await process_prompt(request)


@app.post("/api/conversation/reset")
async def reset_conversation(request: dict):
    conversation_id = request.get("conversation_id")
    if isinstance(conversation_id, str):
        conversation_store.clear(conversation_id)
    return {"status": "reset", "conversation_id": conversation_id}


def _route_signature(route: dict) -> tuple:
    return (
        str(route.get("router_address", "")).lower(),
        str(route.get("pool_address", "")).lower(),
        int(route.get("pool_fee", 0)),
        str(route.get("token_in_address", "")).lower(),
        str(route.get("token_out_address", "")).lower(),
    )


def _same_authority(saved, current: dict) -> bool:
    """Ensure current graph authority still resolves the saved structured operation."""
    if current.get("decision") != Decision.APPROVED.value:
        return False
    if str(current.get("verified_address", "")).lower() != saved.verified_address.lower():
        return False
    if str(current.get("verified_selector", "")).lower() != saved.verified_selector.lower():
        return False
    if saved.action != "swap":
        return (
            str(current.get("verified_asset", "")).lower()
            == str(saved.verified_asset or "").lower()
            and current.get("verified_asset_decimals") == saved.verified_asset_decimals
        )
    current_routes = {
        _route_signature(route)
        for route in current.get("routes") or []
    }
    saved_routes = {_route_signature(route) for route in saved.routes}
    return bool(current_routes) and bool(current_routes & saved_routes)


@app.post("/api/execute")
async def execute(request: ExecuteRequest):
    """Execute only a live server-held approved structured verification result."""
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", request.wallet_address):
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": "INVALID_WALLET_ADDRESS",
                "reason": "Wallet address is invalid",
            },
        }

    operation, claim_status = capability_store.claim_with_status(
        request.verification_id
    )
    if not operation:
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": claim_status,
                "reason": "Verification is missing, expired, or already used",
            },
        }
    if operation.decision != Decision.APPROVED:
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": "VERIFICATION_NOT_APPROVED",
                "reason": "Execution requires an APPROVED verification",
            },
        }
    intent = operation.intent
    checked = validate_candidate(intent)
    if checked.status != Decision.APPROVED:
        return {"decision": "FAILED", "execution": {
            "reason_code": "INVALID_APPROVED_INTENT", "reason": "The saved operation contains unsupported or incomplete intent parameters."}}
    if operation.action == "swap" and (
        type(operation.slippage_bps) is not int or not 1 <= operation.slippage_bps <= 500
        or (intent.slippage_bps is not None and intent.slippage_bps != operation.slippage_bps)
    ):
        return {"decision": "FAILED", "execution": {
            "reason_code": "INVALID_APPROVED_SLIPPAGE", "reason": "The saved slippage is missing or inconsistent; verify the operation again."}}
    current = await asyncio.to_thread(
        verify_intent,
        intent.protocol,
        intent.token_in,
        intent.token_out,
        intent.action,
        intent.chain_id,
    )
    if not _same_authority(operation, current):
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": "APPROVAL_MISMATCH",
                "reason": "The authoritative graph result changed or is no longer current; verify again"
            },
        }

    routes = current.get("routes") or []
    amount_text = format(intent.amount, "f")
    if operation.action == "swap":
        trusted_destinations = {
            current.get("verified_address"),
            *(route.get("token_in_address") for route in routes),
        }
    else:
        trusted_destinations = {current.get("verified_address")}
        if operation.action in {"supply", "repay"}:
            trusted_destinations.add(current.get("verified_asset"))
    try:
        for destination in trusted_destinations:
            if not destination:
                return {
                    "decision": "FAILED",
                    "execution": {
                        "reason_code": "INVALID_EXECUTION_DATA",
                        "reason": "Verified execution data is incomplete",
                    },
                }
            whitelist_result = await asyncio.to_thread(add_to_whitelist, destination)
            if not whitelist_result.get("success"):
                return {
                    "decision": "FAILED",
                    "execution": {
                        "reason_code": whitelist_result.get(
                            "reason_code", "DESTINATION_POLICY_ERROR"
                        ),
                        "reason": f"Whitelist failed: {whitelist_result.get('error', 'unknown error')}"
                    },
                }

        if operation.action == "swap":
            exec_result = await asyncio.to_thread(
                execute_swap,
                routes,
                amount_text,
                operation.slippage_bps,
            )
        else:
            exec_result = await asyncio.to_thread(execute_aave, {
                "action": operation.action,
                "pool_address": current["verified_address"],
                "asset_address": current["verified_asset"],
                "asset_symbol": operation.verified_asset_symbol,
                "asset_decimals": current["verified_asset_decimals"],
                "amount": amount_text,
                "function_signature": current["verified_function"],
                "function_selector": current["verified_selector"],
                "interest_rate_mode": operation.interest_rate_mode,
                "referral_code": operation.referral_code,
            })
    except Exception:
        logger.exception("Structured execution failed")
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": "EXECUTION_ERROR",
                "reason": "Transaction execution failed",
            },
        }

    if not exec_result.get("executed"):
        return {
            "decision": "FAILED",
            "execution": {
                "reason_code": exec_result.get("reason_code", "EXECUTION_FAILED"),
                "reason": exec_result.get("reason", "Execution failed"),
            },
        }
    return {
        "decision": "EXECUTED",
        "execution": {
            "reason_code": "TRANSACTION_SUBMITTED",
            **{
                key: exec_result.get(key)
                for key in (
                    "tx_hash", "smart_wallet", "verified_address", "pool", "pool_fee",
                    "amount_in", "quoted_amount_out", "minimum_amount_out", "token_in",
                    "token_out", "slippage_bps", "asset_address", "action",
                    "interest_rate_mode", "referral_code", "explorer", "latency_ms",
                )
            },
        },
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "network": settings.supported_network,
        "chain_id": settings.supported_chain_id,
        "model": settings.llm_model,
    }
