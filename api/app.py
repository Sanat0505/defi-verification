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

@app.get("/api/health")
async def health():
    return {"status": "ok"}