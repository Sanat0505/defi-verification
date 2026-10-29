"""Read-only browsing of the separate expanded knowledge database."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from knowledge.database import entries, summary

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)
Module = Literal["aave-v3", "aave-umbrella", "uniswap-v3"]
Kind = Literal["operations", "functions", "contracts", "gaps"]
KINDS = {"operations": "Operation", "functions": "Function", "contracts": "Contract", "gaps": "CoverageGap"}


async def read_catalog(function, **kwargs):
    try:
        return await asyncio.to_thread(function, **kwargs)
    except (Neo4jError, ServiceUnavailable, ValueError) as exc:
        logger.warning("Expanded knowledge catalog unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Expanded knowledge is unavailable. Start Neo4j and run 'python -m knowledge sync' to publish its separate database.") from None


@router.get("/api/knowledge/summary")
async def knowledge_summary():
    return await read_catalog(summary)


@router.get("/api/knowledge/{kind}")
async def knowledge_entries(kind: Kind, module: Module | None = None,
                            name: str | None = Query(None, max_length=100),
                            limit: int = Query(100, ge=1, le=200),
                            offset: int = Query(0, ge=0, le=100000)):
    rows = await read_catalog(entries, kind=KINDS[kind], module=module, name=name, limit=limit, offset=offset)
    return {"wallet_eligibility": "not_evaluated", "items": rows, "limit": limit, "offset": offset}


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_browser(request: Request, kind: Kind = "operations",
                            module: str = Query("", max_length=30),
                            name: str = Query("", max_length=100),
                            offset: int = Query(0, ge=0, le=100000)):
    if module and module not in {"aave-v3", "aave-umbrella", "uniswap-v3"}:
        raise HTTPException(422, "Unknown module")
    info = await read_catalog(summary)
    rows = await read_catalog(entries, kind=KINDS[kind], module=module or None, name=name or None, limit=100, offset=offset)
    return templates.TemplateResponse(request=request, name="knowledge.html", context={
        "info": info, "rows": rows, "kind": kind, "module": module, "name": name,
        "offset": offset, "next_url": str(request.url.include_query_params(offset=offset + 100)),
        "previous_url": str(request.url.include_query_params(offset=max(0, offset - 100))),
    })
