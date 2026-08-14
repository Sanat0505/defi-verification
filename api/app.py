import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

from llm.intent_parser import parse_intent
from db.verifier import verify_intent
from wallet.erc4337 import execute_swap, add_to_whitelist

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class PromptRequest(BaseModel):
    prompt: str
    wallet_address: str | None = None

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/verify")
async def verify(req: PromptRequest):
    intent = await parse_intent(req.prompt)
    if "error" in intent:
        return {"decision": "ERROR", "message": intent["error"]}

    result = verify_intent(
        protocol  = intent.get("protocol"),
        token_in  = intent.get("token_in"),
        token_out = intent.get("token_out"),
        action    = intent.get("action", "swap"),
        chain_id  = 11155111
    )
    result["intent"] = intent
    result["wallet"] = req.wallet_address
    return result


@app.post("/api/execute")
async def execute(req: PromptRequest):
    """Execute a verified transaction via ERC-4337 smart wallet."""
    if not req.wallet_address:
        return {
            "decision": "FAILED",
            "execution": {"reason": "Wallet not connected"}
        }

    intent = await parse_intent(req.prompt)
    if "error" in intent:
        return {"decision": "FAILED", "execution": {"reason": intent["error"]}}

    # Verify the intent again (security check)
    result = verify_intent(
        protocol  = intent.get("protocol"),
        token_in  = intent.get("token_in"),
        token_out = intent.get("token_out"),
        action    = intent.get("action", "swap"),
        chain_id  = 11155111
    )

    # If verification failed, don't execute
    if result["decision"] != "APPROVED":
        return {
            "decision": "FAILED",
            "execution": {"reason": result.get("reason", "Verification failed")}
        }

    action = intent.get("action", "swap").lower()
    if action != "swap":
        return {
            "decision": "FAILED",
            "execution": {
                "reason": (
                    f"Real {action} execution is not implemented yet. "
                    "The current execution layer supports Uniswap V3 ERC-20 swaps only."
                )
            },
        }

    amount = intent.get("amount")
    if amount is None:
        return {
            "decision": "FAILED",
            "execution": {"reason": "A swap amount is required"},
        }

    routes = result.get("routes") or []
    if not routes:
        return {
            "decision": "FAILED",
            "execution": {"reason": "The graph returned no executable Uniswap routes"},
        }

    verified_address = result.get("verified_address")
    # The ERC-4337 batch calls the input token for approve() and then the
    # router for exactInputSingle(). Both destinations must originate in the
    # graph result; no client- or LLM-provided address is accepted.
    try:
        trusted_destinations = {
            verified_address,
            *(route.get("token_in_address") for route in routes),
        }
        for destination in trusted_destinations:
            whitelist_result = add_to_whitelist(destination)
            if not whitelist_result.get("success"):
                error_msg = whitelist_result.get("error", "Unknown whitelist error")
                return {
                    "decision": "FAILED",
                    "execution": {"reason": f"Whitelist failed: {error_msg}"}
                }
    except Exception as e:
        return {
            "decision": "FAILED",
            "execution": {"reason": f"Whitelist exception: {str(e)}"}
        }

    # Quote, apply slippage protection, and submit an atomic approve+swap
    # UserOperation. ZeroDev simulates it before sponsorship/broadcast.
    try:
        slippage_bps = int(os.getenv("SWAP_SLIPPAGE_BPS", "100"))
        exec_result = execute_swap(
            routes=routes,
            amount=str(amount),
            slippage_bps=slippage_bps,
        )

        # Success
        if exec_result.get("executed"):
            return {
                "decision": "EXECUTED",
                "execution": {
                    "tx_hash": exec_result.get("tx_hash"),
                    "smart_wallet": exec_result.get("smart_wallet"),
                    "verified_address": verified_address,
                    "pool": exec_result.get("pool"),
                    "pool_fee": exec_result.get("pool_fee"),
                    "amount_in": exec_result.get("amount_in"),
                    "quoted_amount_out": exec_result.get("quoted_amount_out"),
                    "minimum_amount_out": exec_result.get("minimum_amount_out"),
                    "token_in": exec_result.get("token_in"),
                    "token_out": exec_result.get("token_out"),
                    "slippage_bps": exec_result.get("slippage_bps"),
                    "explorer": exec_result.get("explorer"),
                    "latency_ms": exec_result.get("latency_ms", 0)
                }
            }

        # Failed
        return {
            "decision": "FAILED",
            "execution": {"reason": exec_result.get("reason", "Execution failed")}
        }
    except Exception as e:
        return {
            "decision": "FAILED",
            "execution": {"reason": f"Execution error: {str(e)}"}
        }


@app.get("/api/health")
async def health():
    return {"status": "ok", "network": "Ethereum Sepolia", "chain_id": 11155111}
