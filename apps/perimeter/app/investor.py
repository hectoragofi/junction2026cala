"""Reverse due diligence: a founder checks an investor before the meeting.

Everything comes from Cala's graph: the investor's portfolio (INVESTED_IN), its dated deals
(PARTICIPATES_IN_CORPORATE_EVENT as INVESTOR), who it invests alongside (the other investors on those
deals) and whether it backs a rival of the founder's company.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from . import kg
from .cala import CalaError, cala

router = APIRouter(prefix="/api/investor")

PROPS = ["name", "legal_name", "aliases", "website", "description", "headquarters_address", "founding_date"]
OUT = {"INVESTED_IN": 100, "PARTICIPATES_IN_CORPORATE_EVENT": 100, "HAS_HEADQUARTERS_IN": 5}
INC = {"WORKS_AT": 12, "FOUNDED": 6, "IS_EXECUTIVE_OF": 12}
DEALS_SHOWN = 8


async def _investor(eid: str) -> dict:
    try:
        r = await cala.retrieve(eid, PROPS, OUT, INC)
    except CalaError as e:
        raise HTTPException(502, f"Cala could not load this investor: {e}")
    props = r.get("properties") or {}
    rels = r.get("relationships") or {}
    out = {k: [kg._edge(x) for x in v or [] if x.get("id")] for k, v in (rels.get("outgoing") or {}).items()}
    inc = {k: [kg._edge(x) for x in v or [] if x.get("id")] for k, v in (rels.get("incoming") or {}).items()}

    def pv(k):
        v = props.get(k)
        return v.get("value") if isinstance(v, dict) else None

    return {"id": r.get("id") or eid, "name": kg.clean_name(r.get("name") or ""),
            "description": r.get("description") or pv("description") or "", "website": pv("website"),
            "founded": str(pv("founding_date") or "")[:4] or None, "out": out, "inc": inc}


def _portfolio(inv: dict) -> list[dict]:
    """Companies the investor backs, name variants merged (Cala often holds several legal entities)."""
    merged: list[dict] = []
    for e in inv["out"].get("INVESTED_IN", []):
        name = kg.short_company(kg.clean_name(e["name"]))
        hit = next((m for m in merged if m["id"] == e["id"] or kg.same_org(m["name"], name)), None)
        if hit:
            hit["sources"] = kg.merge_sources(hit["sources"], e["sources"])
            hit["ids"].append(e["id"])
        else:
            merged.append({"id": e["id"], "ids": [e["id"]], "name": name, "sources": kg.merge_sources(e["sources"])})
    return sorted(merged, key=lambda m: m["name"].lower())


def _deal_edges(inv: dict) -> list[dict]:
    edges = [e for e in inv["out"].get("PARTICIPATES_IN_CORPORATE_EVENT", [])
             if (e.get("role") or "").upper() == "INVESTOR" and e.get("date")]
    return sorted(edges, key=lambda e: e["date"], reverse=True)


def _activity(edges: list[dict]) -> dict:
    today = date.today()
    cutoff = (today - timedelta(days=365)).isoformat()
    years = Counter(e["date"][:4] for e in edges)
    span = range(today.year - 5, today.year + 1)
    return {"deals": len(edges), "last_12m": sum(1 for e in edges if e["date"] >= cutoff),
            "last_deal": edges[0]["date"] if edges else None,
            "by_year": [{"year": str(y), "n": years.get(str(y), 0)} for y in span]}


@router.get("/search")
async def search(q: str):
    q = q.strip()
    if len(q) < 2:
        return {"results": []}
    try:
        res = await cala.search(q, ["Company", "Organization"])
    except CalaError as e:
        raise HTTPException(502, f"Cala search failed: {e}")
    scored = sorted(res, key=lambda e: -kg.similarity(q, e.get("name") or ""))
    return {"results": [{"id": e["id"], "name": kg.clean_name(e.get("name") or ""),
                         "description": kg.trim_text(e.get("description"), 110)} for e in scored[:6]]}


@router.get("/{eid}")
async def profile(eid: str):
    inv = await _investor(eid)
    edges = _deal_edges(inv)
    people = []
    for rel in ("FOUNDED", "IS_EXECUTIVE_OF", "WORKS_AT"):
        for e in inv["inc"].get(rel, []):
            if e["type"] == "Person" and not any(p["id"] == e["id"] for p in people):
                people.append({"id": e["id"], "name": kg.clean_name(e["name"]), "role": e.get("role")})
    hq = next((e["name"] for e in inv["out"].get("HAS_HEADQUARTERS_IN", [])), None)
    return {"id": inv["id"], "name": inv["name"], "description": kg.trim_text(inv["description"], 90), "website": inv["website"],
            "founded": inv["founded"], "hq": hq, "portfolio": _portfolio(inv), "activity": _activity(edges),
            "people": people[:8]}


def _issuer(ev: dict, investor: str) -> str | None:
    name = next((p["name"] for p in ev["participants"] if (p.get("role") or "").upper() == "ISSUER"), None)
    if not name:  # Cala's event description starts with the company: "Anthropic PBC. Round: Series H. ..."
        m = re.match(r"\s*(.+?)\.\s+Round:", ev.get("description") or "")
        name = m.group(1) if m else None
    return kg.short_company(kg.clean_name(name)) if name and not kg.same_org(name, investor) else None


def _amount(ev: dict) -> str | None:
    if ev.get("amount"):
        return ev["amount"]
    m = re.search(r"amount raised:\s*([\d.]+)\s*([A-Z]{3})", ev.get("description") or "")
    return kg.fmt_amount(float(m.group(1)), m.group(2)) if m else None


@router.get("/{eid}/deals")
async def deals(eid: str):
    """The latest deals in detail, plus who this investor shows up next to on them."""
    inv = await _investor(eid)
    edges = _deal_edges(inv)[:DEALS_SHOWN]
    events = await asyncio.gather(*[kg.fetch_event(e) for e in edges])
    rows, along = [], Counter()
    refs: dict[str, dict] = {}
    for edge, ev in zip(edges, events):
        if not ev:
            continue
        co = []
        for p in ev["participants"]:
            name = kg.clean_name(p["name"])
            if (p.get("role") or "").upper() != "INVESTOR" or p["id"] == inv["id"] or kg.same_org(name, inv["name"]):
                continue
            if name not in co:
                co.append(name)
                along[name] += 1
                refs.setdefault(name, {"id": p["id"], "name": name})
        rows.append({"id": ev["id"], "date": ev.get("date") or edge["date"], "company": _issuer(ev, inv["name"]),
                     "round": ev.get("round") or kg._round_from_desc(ev.get("description") or ""),
                     "amount": _amount(ev), "co_investors": co, "sources": ev["sources"]})
    alongside = [{**refs[n], "deals": c} for n, c in along.most_common(8)]
    return {"deals": rows, "alongside": alongside, "of": len(_deal_edges(inv))}


@router.get("/{eid}/conflicts")
async def conflicts(eid: str, me: str):
    """Does this investor back a rival of the founder's company?"""
    inv = await _investor(eid)
    best, _, _ = await kg.resolve_company(me.strip())
    if not best:
        raise HTTPException(404, f"Cala has no company called {me.strip()}")
    ent = await kg.safe_entity(best["id"])
    if not ent:
        raise HTTPException(502, "Cala could not load your company")
    company = kg.company_basics(ent)
    rivals = await kg.find_rivals(company)
    portfolio = _portfolio(inv)

    def held(name: str, rid: str | None = None) -> dict | None:
        return next((p for p in portfolio if rid in p["ids"] or kg.same_org(p["name"], name)), None)

    hits = []
    for r in rivals:
        p = held(r["name"], r["id"])
        if p:
            hits.append({"id": r["id"], "name": r["name"], "portfolio_id": p["id"], "sources": p["sources"]})
    return {"company": {"id": company["id"], "name": company["name"]},
            "already_investor": bool(held(company["name"], company["id"])),
            "rivals": [{"id": r["id"], "name": r["name"]} for r in rivals], "conflicts": hits,
            "portfolio_size": len(portfolio)}


@router.get("/{eid}/ask")
async def ask(eid: str, q: str):
    """A free question about this investor, answered by Cala's knowledge search with its sources."""
    q = q.strip()
    if not q:
        raise HTTPException(400, "Ask a question")
    inv = await _investor(eid)
    try:
        res = await cala.ksearch(f"{q} (about the investor {inv['name']})")
    except CalaError as e:
        raise HTTPException(502, f"Cala could not answer: {e}")
    return {"answer_md": res.get("content") or "", "sources": kg._ks_sources(res.get("context") or [])}
