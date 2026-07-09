import os
from urllib import request
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

from llm.intent_parser import parse_intent
from db.verifier import verify_intent
from wallet.erc4337 import execute as execute_userops, add_to_whitelist

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
        action    = intent.get("action", "swap")
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
        action    = intent.get("action", "swap")
    )

    # If verification failed, don't execute
    if result["decision"] != "APPROVED":
        return {
            "decision": "FAILED",
            "execution": {"reason": result.get("reason", "Verification failed")}
        }

    verified_address = result.get("verified_address")
    wallet_address = req.wallet_address

    # Step 1: Add wallet to session whitelist
    try:
        whitelist_result = add_to_whitelist(wallet_address)
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

    # Step 2: Execute UserOperation via ERC-4337
    try:
        amount_eth = float(intent.get("amount", 0.001))
        action = intent.get("action", "swap")
        exec_result = execute_userops(
            verified_address=verified_address,
            amount_eth=amount_eth,
            action=action
        )

        # Success
        if exec_result.get("executed"):
            return {
                "decision": "EXECUTED",
                "execution": {
                    "tx_hash": exec_result.get("tx_hash"),
                    "smart_wallet": exec_result.get("smart_wallet"),
                    "verified_address": verified_address,
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
    return {"status": "ok"}