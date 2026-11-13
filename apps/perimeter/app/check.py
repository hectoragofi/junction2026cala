"""One-off company check, streamed as steps and partial sections (as each Cala call lands), then a result."""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from . import kg
from .kg import (clean_name, company_basics, company_events, event_label, investors_of, merge_sources,
                 people_of, safe_entity, same_org, short_company)
from .perimeter import screen_hint

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

STEPS = [("match", "Matching the company"), ("profile", "Reading Cala profile"),
         ("people", "Mapping people and owners"), ("events", "Reading corporate events"),
         ("rivals", "Finding closest rivals"), ("screen", "Screening sanctions and news")]
LABEL = dict(STEPS)
RIVALS_DEADLINE = 75.0  # seconds from check start
SCREEN_DEADLINE = 100.0
PEOPLE_CAP = 6  # person lookups per check
EVENTS_CAP = 8  # corporate-event lookups per check


def _period() -> str:
    now = datetime.now()
    start = now - timedelta(days=365)
    return f"{start.day} {start:%b %Y} – {now.day} {now:%b %Y}"


async def run_check(q: str, portfolio_ids: set[str], portfolio_names: list[str]) -> AsyncIterator[tuple[str, dict]]:
    t0 = time.monotonic()

    def step(key, status, detail=None):
        d = {"key": key, "label": LABEL[key], "status": status}
        if detail:
            d["detail"] = detail
        return ("step", d)

    q = (q or "").strip()
    yield step("match", "running")
    if not q:
        yield step("match", "error", "Empty query")
        yield ("error", {"message": "Type a company name."})
        return
    if UUID.match(q):
        ent = await safe_entity(q)
        conf = 1.0
    else:
        best, cands, conf = await kg.resolve_company(q)
        ent = await safe_entity(best["id"]) if best else None
    if not ent or ent["type"] not in kg.COMPANY_TYPES:
        yield step("match", "error", "Not found in Cala")
        yield ("error", {"message": f"Cala has no company matching “{q}”."})
        return
    c = company_basics(ent)
    yield step("match", "done", f"{c['name']}" + (f" · {c['hq']}" if c.get("hq") else ""))
    tags = [t for t in [c.get("industry"), c.get("country"), f"Founded {c['founded']}" if c.get("founded") else None]
            if t]
    company = {k: c.get(k) for k in ("id", "name", "description", "website", "hq", "founded", "industry")}
    company["legal_name"] = kg.pval(ent, "legal_name")
    company["lei"] = kg.pval(ent, "lei")
    company["tags"] = tags
    yield ("partial", {"section": "company", "data": company})

    # Everything below runs in parallel and streams as it lands; the page renders from the first partial.
    # Calls are ordered by value and capped (~25 per check): profile (no extra call), people (<= PEOPLE_CAP),
    # events (<= EVENTS_CAP), screening (1), rivals (1 query + name matching, last and never blocking).
    screen_task = asyncio.create_task(kg.screen(c["name"], screen_hint(c)))
    events_task = asyncio.create_task(company_events(ent, cap=EVENTS_CAP))
    rivals_task = asyncio.create_task(kg.find_rivals(c, cap=5))

    # profile: already in the entity record
    yield step("profile", "running")
    facts = []

    def fact(label, value, sources):
        if value:
            facts.append({"label": label, "value": str(value), "sources": sources[:3]})

    fact("Legal name", kg.pval(ent, "legal_name"), kg.psrc(ent, "legal_name"))
    reg = ent["out"].get("IS_REGISTERED_IN", [])
    reg_c = next((e for e in reg if e["type"] == "Country"), reg[0] if reg else None)
    if reg_c:
        fact("Registered in", reg_c["name"], reg_c["sources"])
    hq_e = next((e for e in ent["out"].get("HAS_HEADQUARTERS_IN", []) if e["type"] == "Country"), None)
    fact("Headquarters", c.get("hq") or kg.pval(ent, "headquarters_address"),
         kg.psrc(ent, "headquarters_address") or (hq_e or {}).get("sources", []))
    inds = ent["out"].get("OPERATES_IN_INDUSTRY", [])
    if inds:
        fact("Industry", ", ".join(kg.title_industry(e["name"]) for e in inds[:3]), inds[0]["sources"])
    fact("Founded", kg.pval(ent, "founding_date"), kg.psrc(ent, "founding_date"))
    fact("LEI", kg.pval(ent, "lei"), kg.psrc(ent, "lei"))
    fact("Website", kg.pval(ent, "website"), kg.psrc(ent, "website"))
    yield ("partial", {"section": "facts", "data": facts})
    yield step("profile", "done", f"{len(facts)} sourced facts")

    people = people_of(ent)[:12]
    parents: list[dict] = []
    for rel in ("IS_ULTIMATE_PARENT_OF", "IS_DIRECT_PARENT_OF", "IS_BENEFICIARY_OWNER_OF"):
        for e in ent["inc"].get(rel, []):
            if any(o["id"] == e["id"] for o in parents):
                continue
            parents.append({"id": e["id"], "name": short_company(e["name"]),
                            "note": {"IS_ULTIMATE_PARENT_OF": "Ultimate parent", "IS_DIRECT_PARENT_OF": "Parent",
                                     "IS_BENEFICIARY_OWNER_OF": "Beneficial owner"}[rel]})
    plain_people = [{"id": p["id"], "name": p["name"], "role": p["role"]} for p in people]

    async def people_job():
        pents = await asyncio.gather(*[safe_entity(p["id"], 30) for p in people[:PEOPLE_CAP]])
        out = []
        for p, pe in zip(people, list(pents) + [None] * (len(people) - len(pents))):
            note = None
            if pe:
                others = []
                for rel, lst in pe["out"].items():
                    for e in lst:
                        if e["type"] in kg.COMPANY_TYPES and e["id"] != ent["id"] and \
                                not same_org(e["name"], ent["name"]):
                            others.append((rel, e))
                hit = next(((r, e) for r, e in others if e["id"] in portfolio_ids or any(
                    same_org(e["name"], n) for n in portfolio_names)), None)
                pick = hit or next(((r, e) for r, e in others
                                    if r in ("IS_BOARD_MEMBER_OF", "FOUNDED", "IS_CEO_OF")), None)
                if pick:
                    r, e = pick
                    what = {"IS_BOARD_MEMBER_OF": "on {}'s board", "FOUNDED": "founded {}",
                            "IS_CEO_OF": "CEO of {}"}.get(r, "linked to {}")
                    note = "Also " + what.format(short_company(e["name"])) + (" (in your portfolio)" if hit else "")
            d = {"id": p["id"], "name": p["name"], "role": p["role"]}
            if note:
                d["note"] = note
            out.append(d)
        return out

    async def rivals_job():
        try:
            return await asyncio.wait_for(asyncio.shield(rivals_task),
                                          max(5.0, RIVALS_DEADLINE - (time.monotonic() - t0))), False
        except asyncio.TimeoutError:
            return [], True
        except Exception:
            return [], False

    async def screen_job():
        try:
            return await asyncio.wait_for(asyncio.shield(screen_task),
                                          max(5.0, SCREEN_DEADLINE - (time.monotonic() - t0)))
        except (asyncio.TimeoutError, Exception):
            return None

    # what the profile already knows renders now; notes and investors fill in as their calls land
    yield ("partial", {"section": "people", "data": plain_people, "pending": True})
    yield ("partial", {"section": "ownership", "data": parents, "pending": True})
    for k in ("people", "events", "screen", "rivals"):
        yield step(k, "running")
    jobs = {asyncio.create_task(people_job()): "people", events_task: "events",
            asyncio.create_task(screen_job()): "screen", asyncio.create_task(rivals_job()): "rivals"}
    out_people, ownership, funding, rv, scr, events = plain_people, list(parents), [], [], None, []
    pending = set(jobs)
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            key = jobs[t]
            try:
                val = t.result()
            except Exception:
                val = None
            if key == "people":
                out_people = val or plain_people
                yield ("partial", {"section": "people", "data": out_people})
                yield step("people", "done", f"{len(out_people)} people")
            elif key == "events":
                events = val or []
                ownership = list(parents)
                for i in investors_of(ent, events)[:12]:
                    note = i["sub"]
                    rs = [r["round"] for r in i["rounds"] if r.get("round")]
                    if rs:
                        note = f"{i['sub']} · {rs[-1]}"
                    ownership.append({"id": i["id"], "name": i["name"], "note": note})
                funding = []
                for ev in events:
                    if ev["kind"] not in ("funding", "mna", "ipo"):
                        continue
                    if ev["kind"] == "funding" and (ev.get("role") or "").upper() == "INVESTOR":
                        continue
                    d = {"date": ev.get("date"), "label": event_label(ev, ent["name"], ev.get("role")),
                         "sources": ev["sources"][:3]}
                    if ev.get("amount"):
                        d["amount"] = ev["amount"]
                    funding.append(d)
                funding.sort(key=lambda f: f.get("date") or "", reverse=True)
                yield ("partial", {"section": "ownership", "data": ownership})
                yield ("partial", {"section": "funding", "data": funding})
                yield step("events", "done", f"{len(funding)} corporate events, {len(ownership)} owners and investors")
            elif key == "rivals":
                rivals, late = val or ([], False)
                rv = [{"id": r["id"], "name": r["name"], "sub": r.get("sub"),
                       "in_portfolio": r["id"] in portfolio_ids or any(same_org(r["name"], n)
                                                                       for n in portfolio_names)}
                      for r in rivals]
                yield ("partial", {"section": "rivals", "data": rv, **({"late": True} if late else {})})
                yield step("rivals", "done", ", ".join(r["name"] for r in rv[:3]) if rv else (
                    "Still loading from Cala, run the check again shortly" if late else "None found"))
            elif key == "screen":
                scr = val or {"findings": [], "screened": 0, "unavailable": True,
                              "sanctions": {"clear": True, "screened": 0, "text": "Screening unavailable",
                                            "sources": []}}
                findings = _findings(scr)
                yield ("partial", {"section": "screen", "data": {
                    "findings": findings, "sanctions": scr["sanctions"], "counts": _counts(findings),
                    "unavailable": bool(scr.get("unavailable"))}})
                yield step("screen", "done", f"{len(findings)} finding{'s' if len(findings) != 1 else ''} · "
                                             f"{scr['screened']} sources screened")

    findings = _findings(scr)
    n_facts = len(facts) + len(funding) + len(out_people) + len(ownership) + sum(len(f["sources"]) for f in findings)
    n_ents = 1 + len(out_people) + len(ownership) + len(rv) + len(events)
    yield ("result", {
        "company": company, "checked_at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.monotonic() - t0, 1), "period": _period(),
        "counts": _counts(findings), "stats": {"facts": n_facts, "entities": n_ents},
        "findings": findings, "sanctions": scr["sanctions"], "facts": facts, "people": out_people,
        "ownership": ownership, "funding": funding, "rivals": rv,
    })


def _findings(scr: dict) -> list[dict]:
    return [{k: f[k] for k in ("severity", "status", "category", "title", "body", "sources")} | (
        {"date": f["date"]} if f.get("date") else {}) for f in scr["findings"]]


def _counts(findings: list[dict]) -> dict:
    return {s: sum(1 for f in findings if f["severity"] == s) for s in ("high", "medium", "low")}
