"""Perimeter API (FastAPI). Serves web/ at / and the API under /api."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import kg
from .cala import CACHE_DIR, PERIMETER_DIR, cala
from .check import run_check
from .perimeter import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("perimeter")

WEB_DIR = PERIMETER_DIR / "web"
STATE_FILE = CACHE_DIR / "state.json"

# Real companies Cala knows well, chosen for overlapping investors, M&A and recent rounds.
DEMO_PORTFOLIO = [
    "327d0698-9bb0-4250-a2fd-a5d9cb5a6810",  # Mollie (Amsterdam payments)
    "151397f7-1f81-45a7-9cce-9ba4956d52a5",  # Qonto (Paris business banking)
    "416166a8-95e7-4cd6-baad-3208cb8d4299",  # Pennylane (Paris accounting)
    "11267552-e210-40ec-aafd-526c205f6225",  # Pigment (Paris planning software)
]

STATE: dict = {"portfolio": [], "portfolio_ids": [], "built": None, "built_at": None}
BUILD: dict = {"task": None, "progress": None, "error": None}


def load_state():
    if STATE_FILE.exists():
        try:
            STATE.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("state load failed: %s", e)


def save_state():
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


async def _company_card(eid: str) -> dict | None:
    ent = await kg.safe_entity(eid)
    if not ent:
        return None
    c = kg.company_basics(ent)
    return {k: c.get(k) for k in ("id", "name", "description", "website", "hq", "founded")}


async def _build(ids: list[str]):
    BUILD["error"] = None
    try:
        res = await build(ids, progress=lambda m: BUILD.__setitem__("progress", m))
        STATE["built"] = res
        STATE["built_at"] = res["built_at"]
        if res.get("portfolio"):
            STATE["portfolio"] = res["portfolio"]
        save_state()
        log.info("perimeter built in %ss", res.get("build_seconds"))
    except Exception as e:  # keep the previous build
        log.exception("build failed")
        BUILD["error"] = str(e)
    finally:
        BUILD["progress"] = None


def start_build(ids: list[str]):
    t = BUILD.get("task")
    if t and not t.done():
        t.cancel()
    BUILD["task"] = asyncio.create_task(_build(ids))


def building() -> bool:
    t = BUILD.get("task")
    return bool(t and not t.done())


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_state()
    if STATE.get("portfolio_ids") and not STATE.get("built"):
        start_build(STATE["portfolio_ids"])
    yield
    await cala.close()


app = FastAPI(title="Perimeter", lifespan=lifespan)


# --------------------------------------------------------------------------- API
@app.get("/api/health")
async def health():
    return {"ok": True, "cala": bool(cala.key), "cache": cala.stats}


class ResolveIn(BaseModel):
    text: str


def _split_names(text: str) -> list[str]:
    out = []
    for part in re.split(r"[,\n;]+", text or ""):
        p = part.strip()
        if not p:
            continue
        if re.match(r"^(https?://)?([\w-]+\.)+[a-z]{2,}(/.*)?$", p, re.I):
            host = urlparse(p if "//" in p else "//" + p).hostname or p
            host = re.sub(r"^www\.", "", host)
            p = host.split(".")[-2] if host.count(".") >= 1 else host
            p = p.replace("-", " ")
        out.append(p[:100])
    return list(dict.fromkeys(out))[:20]


@app.post("/api/resolve")
async def resolve(body: ResolveIn):
    names = _split_names(body.text)

    async def one(n):
        best, cands, conf = await kg.resolve_company(n)
        card = await _company_card(best["id"]) if best else None
        cc = [{"id": c["id"], "name": kg.short_company(c.get("name", "")), "description": c.get("description") or ""}
              for c in cands if not best or c["id"] != best["id"]][:4]
        return {"query": n, "best": card, "candidates": cc, "confidence": round(conf, 2)}

    return {"matches": await asyncio.gather(*[one(n) for n in names])}


@app.get("/api/portfolio")
async def get_portfolio():
    return {"companies": STATE.get("portfolio") or [], "building": building(), "built_at": STATE.get("built_at"),
            "progress": BUILD.get("progress"), "error": BUILD.get("error")}


class PortfolioIn(BaseModel):
    ids: list[str]


@app.post("/api/portfolio")
async def set_portfolio(body: PortfolioIn):
    ids = list(dict.fromkeys(i for i in body.ids if i))[:12]
    if not ids:
        raise HTTPException(400, "ids required")
    cards = [c for c in await asyncio.gather(*[_company_card(i) for i in ids]) if c]
    STATE.update({"portfolio_ids": ids, "portfolio": cards, "built": None, "built_at": None})
    save_state()
    start_build(ids)
    return {"ok": True}


@app.post("/api/portfolio/demo")
async def demo_portfolio():
    if STATE.get("portfolio_ids") == DEMO_PORTFOLIO and STATE.get("built"):
        return {"ok": True}
    return await set_portfolio(PortfolioIn(ids=DEMO_PORTFOLIO))


@app.post("/api/rebuild")
async def rebuild():
    if not STATE.get("portfolio_ids"):
        raise HTTPException(400, "no portfolio")
    start_build(STATE["portfolio_ids"])
    return {"ok": True}


def _empty_perimeter():
    return {"companies": [], "stats": {"rivals": 0, "investors": 0, "people": 0, "countries": 0, "entities": 0,
                                       "facts": 0}, "signals": []}


@app.get("/api/perimeter")
async def perimeter():
    b = STATE.get("built")
    if not b:
        return {**_empty_perimeter(), "building": building()}
    return {**b["perimeter"], "building": building(), "built_at": STATE.get("built_at")}


@app.get("/api/feed")
async def feed():
    b = STATE.get("built")
    if not b:
        n = len(STATE.get("portfolio") or [])
        return {"summary": "Mapping your perimeter…" if building() else "Add companies to start watching.",
                "items": [], "building": building()}
    return {**b["feed"], "building": building(), "built_at": STATE.get("built_at")}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/check/stream")
async def check_stream(q: str, request: Request):
    pids = set(STATE.get("portfolio_ids") or [])
    pnames = [c["name"] for c in STATE.get("portfolio") or []]

    async def gen():
        try:
            async for ev, data in run_check(q, pids, pnames):
                if await request.is_disconnected():
                    return
                yield _sse(ev, data)
        except Exception as e:
            log.exception("check failed")
            yield _sse("error", {"message": f"Check failed: {e}"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class AskIn(BaseModel):
    q: str


def ask_payload(res: dict) -> dict:
    ctx = res.get("context") or []
    sources = []
    for k in ctx:
        for o in k.get("origins") or []:
            d = o.get("document") or {}
            s = o.get("source") or {}
            sources.append({"name": d.get("name") or s.get("name") or "Source", "url": d.get("url") or s.get("url"),
                            "date": None})
    sources = kg.merge_sources(sources, cap=12)
    ents = []
    seen = set()
    for e in res.get("entities") or []:
        if e.get("id") in seen or e.get("entity_type") in ("GPE", "Municipality", "Country", "CountrySubdivision"):
            continue
        seen.add(e.get("id"))
        t = e.get("entity_type") or "Entity"
        ents.append({"id": e.get("id"), "name": e.get("name"),
                     "type": "Company" if t in kg.COMPANY_TYPES else t})
    return {"answer_md": res.get("content") or "", "sources": sources, "entities": ents[:20]}


@app.post("/api/ask")
async def ask(body: AskIn):
    q = (body.q or "").strip()
    if not q:
        raise HTTPException(400, "q required")
    t0 = time.monotonic()
    try:
        res = await cala.ksearch(q)
    except Exception as e:
        raise HTTPException(502, f"Cala: {e}")
    return {**ask_payload(res), "seconds": round(time.monotonic() - t0, 1)}


class DraftIn(BaseModel):
    item_id: str


def _template_note(it: dict) -> dict:
    company = it["company"]["name"]
    subj = it["title"]
    lines = [f"Hi {company} team,", ""]
    lines.append(f"Flagging something from our portfolio watch: {it['title'].rstrip('.')}.")
    if it.get("body"):
        lines += ["", it["body"].strip()]
    when = f" (dated {it['date']})" if it.get("date") else ""
    status = {"confirmed": "Cala lists this as a sourced fact", "reported": "This was reported in the press",
              "possible": "This is a possible match we have not confirmed"}.get(it.get("status"), "")
    if status:
        lines += ["", f"{status}{when}."]
    srcs = [s for s in it.get("sources") or [] if s.get("url")][:3]
    if srcs:
        lines += ["", "Sources:"] + [f"- {s['name']}: {s['url']}" for s in srcs]
    ask_line = {"overlap_investor": "Worth a quick chat about information rights and board access?",
                "overlap_board": "Worth a quick chat about how you handle this?",
                "hiring": "Worth a quick chat about how you handle this?",
                "funding": "Curious how you read this and whether it changes your plans.",
                "mna": "Curious how you read this and whether it changes your plans.",
                }.get(it["kind"], "Is this on your radar? Happy to help if useful.")
    lines += ["", ask_line, "", "Best,"]
    return {"subject": f"Heads-up: {subj}"[:120], "body": "\n".join(lines)}


async def _polish(note: dict, it: dict) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return note
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=key)
        facts = json.dumps({k: it.get(k) for k in ("title", "body", "date", "status", "sources", "company",
                                                   "subject")}, ensure_ascii=False)
        msg = await asyncio.wait_for(client.messages.create(
            model="claude-sonnet-5-5", max_tokens=600,
            system="You polish short notes from a VC to a portfolio founder. Plain, warm, concise (under 120 words). "
                   "Use only the facts given. Keep the source URLs. Return only the note body.",
            messages=[{"role": "user", "content": f"Facts: {facts}\n\nDraft:\n{note['body']}"}]), timeout=20)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if text:
            return {"subject": note["subject"], "body": text}
    except Exception as e:
        log.warning("draft polish failed: %s", e)
    return note


@app.post("/api/draft")
async def draft(body: DraftIn):
    b = STATE.get("built") or {}
    it = next((i for i in (b.get("feed") or {}).get("items", []) if i["id"] == body.item_id), None)
    if not it:
        raise HTTPException(404, "item not found")
    return await _polish(_template_note(it), it)


@app.get("/api/entity/{eid}")
async def entity(eid: str):
    ent = await kg.safe_entity(eid)
    if not ent:
        raise HTTPException(404, "entity not found")
    facts = []
    for k, v in ent["props"].items():
        if k in ("name", "description") or v["value"] in (None, ""):
            continue
        val = v["value"]
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val[:5])
        facts.append({"label": k.replace("_", " ").capitalize(), "value": str(val), "sources": v["sources"][:3]})
    rels = {}
    for d in ("out", "inc"):
        for rel, lst in ent[d].items():
            key = rel if d == "out" else f"{rel} (incoming)"
            refs = []
            for e in lst[:15]:
                r = kg.entity_ref(e)
                if e["type"] in kg.EVENT_TYPES:
                    r["name"] = (e["name"] or "").replace("_", " ").capitalize()
                    if e.get("date"):
                        r["sub"] = e["date"]
                elif e.get("role"):
                    r["sub"] = e["role"]
                refs.append(r)
            rels[key] = refs
    t = ent["type"]
    return {"id": ent["id"], "name": kg.clean_name(ent["name"]), "type": "Company" if t in kg.COMPANY_TYPES else t,
            "description": ent["description"], "facts": facts, "relations": rels}


# --------------------------------------------------------------------------- static web
@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def web(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if WEB_DIR.exists():
        f = (WEB_DIR / path).resolve()
        if path and f.is_file() and WEB_DIR.resolve() in f.parents:
            return FileResponse(f, headers={"Cache-Control": "no-cache"})
        idx = WEB_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"ok": True, "msg": "Perimeter API. Frontend not built yet."})
