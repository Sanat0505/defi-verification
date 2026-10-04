"""FastAPI surface for interpretation, graph verification, and safe execution."""

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
from db.connection import close_driver
from db.verifier import verify_intent
from services.pipeline import process_prompt
from wallet.erc4337 import add_to_whitelist, execute_aave, execute_swap


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_driver()


app = FastAPI(
    title="DeFi Relationship Verification Prototype",
    lifespan=lifespan,
)
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
        (
            str(route.get("router_address", "")).lower(),
            str(route.get("pool_address", "")).lower(),
            int(route.get("pool_fee", 0)),
            str(route.get("token_in_address", "")).lower(),
            str(route.get("token_out_address", "")).lower(),
        )
        for route in current.get("routes") or []
    }
    saved_routes = {
        (
            str(route.get("router_address", "")).lower(),
            str(route.get("pool_address", "")).lower(),
            int(route.get("pool_fee", 0)),
            str(route.get("token_in_address", "")).lower(),
            str(route.get("token_out_address", "")).lower(),
        )
        for route in saved.routes
    }
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
                int(os.getenv("SWAP_SLIPPAGE_BPS", "100")),
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
