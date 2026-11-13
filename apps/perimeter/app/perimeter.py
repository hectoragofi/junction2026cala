"""Perimeter builder: portfolio -> rivals, investors, people, events -> overlaps, signals, feed."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from . import kg
from .kg import (clean_name, company_basics, company_events, entity_ref, event_label, fetch_entity,
                 investors_of, merge_sources, months_ago, norm_key, people_of, safe_entity, same_org,
                 short_company)

log = logging.getLogger("perimeter")

PEOPLE_FETCH_CAP = 10
INVESTOR_FETCH_CAP = 14
RIVAL_CAP = 5


def screen_hint(c: dict) -> str | None:
    bits = [b for b in ((c.get("industry") or "").lower() or None, c.get("country")) if b]
    return " company, ".join(bits) if len(bits) == 2 else (bits[0] if bits else None)


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


async def build_company(eid: str, rival: bool = False) -> dict | None:
    ent = await safe_entity(eid)
    if not ent:
        return None
    c = company_basics(ent)
    c["screen_name"] = c["name"]
    events = await company_events(ent, cap=6 if rival else 10)
    c["events"] = events
    c["investors"] = investors_of(ent, events)
    c["people"] = people_of(ent)
    c["entity"] = {"inc": {k: [e["id"] for e in v] for k, v in ent["inc"].items()},
                   "out": {k: [e["id"] for e in v] for k, v in ent["out"].items()}}
    c["facts_count"] = sum(1 for v in ent["props"].values() if v["sources"]) + sum(
        len(v) for v in ent["out"].values()) + sum(len(v) for v in ent["inc"].values())
    c["prop_sources"] = {k: v["sources"][:3] for k, v in ent["props"].items()}
    return c


async def build(portfolio_ids: list[str], progress=None) -> dict:
    t0 = datetime.now(timezone.utc)

    def say(msg):
        log.info(msg)
        if progress:
            progress(msg)

    say("portfolio")
    port = [c for c in await asyncio.gather(*[build_company(i) for i in portfolio_ids]) if c]
    port_ids = {c["id"] for c in port}

    say("rivals")
    async def rivals_for(c):
        try:
            return await asyncio.wait_for(kg.find_rivals(c, cap=RIVAL_CAP + 1), 240)
        except Exception:
            return []
    rival_lists = await asyncio.gather(*[rivals_for(c) for c in port])
    for c, rl in zip(port, rival_lists):
        c["rivals"] = [r for r in rl if r["id"] not in port_ids and not any(
            same_org(r["name"], p["name"]) for p in port)][:RIVAL_CAP]
        c["rivals_in_portfolio"] = [r for r in rl if r["id"] in port_ids]
    rival_ids = list(dict.fromkeys(r["id"] for c in port for r in c["rivals"]))
    rivals = {c["id"]: c for c in await asyncio.gather(*[build_company(i, rival=True) for i in rival_ids]) if c}
    for c in port:
        for r in c["rivals"]:
            if r["id"] in rivals and kg.similarity(r["name"], rivals[r["id"]]["name"]) >= 0.6:
                rivals[r["id"]]["name"] = r["name"]  # the name Cala's answer used, e.g. "Checkout.com"

    # people of portfolio companies: fetch their other affiliations
    say("people")
    people_ids = list(dict.fromkeys(p["id"] for c in port for p in c["people"][:PEOPLE_FETCH_CAP]))
    inv_ids = list(dict.fromkeys(i["id"] for c in port for i in c["investors"][:INVESTOR_FETCH_CAP]
                                 if i["type"] != "Person"))
    screen_tasks = [kg.screen(c["screen_name"], screen_hint(c)) for c in port]
    rival_screen_tasks = [kg.screen(r["screen_name"], screen_hint(r), only_cached=True) for r in rivals.values()]
    persons, investors_ents, screens, rival_screens = await asyncio.gather(
        asyncio.gather(*[safe_entity(i, 40) for i in people_ids]),
        asyncio.gather(*[safe_entity(i, 80) for i in inv_ids]),
        asyncio.gather(*screen_tasks),
        asyncio.gather(*rival_screen_tasks),
    )
    persons = {p["id"]: p for p in persons if p}
    inv_ents = {e["id"]: e for e in investors_ents if e}
    say("overlaps")
    result = compute(port, rivals, persons, inv_ents, dict(zip([c["id"] for c in port], screens)),
                     dict(zip(rivals.keys(), rival_screens)))
    result["built_at"] = datetime.now(timezone.utc).isoformat()
    result["build_seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    return result


# --------------------------------------------------------------------------- overlap computation
def compute(port: list[dict], rivals: dict[str, dict], persons: dict[str, dict], inv_ents: dict[str, dict],
            screens: dict[str, dict | None], rival_screens: dict[str, dict | None]) -> dict:
    universe: dict[str, dict] = {}  # company id -> {name, kind, of}
    for c in port:
        universe[c["id"]] = {"name": c["name"], "kind": "portfolio", "id": c["id"]}
    rival_of: dict[str, list[str]] = {}
    for c in port:
        for r in c["rivals"]:
            if r["id"] in rivals:
                rival_of.setdefault(r["id"], []).append(c["id"])
                universe.setdefault(r["id"], {"name": rivals[r["id"]]["name"], "kind": "rival", "id": r["id"]})

    def find_company(eid: str, name: str) -> str | None:
        if eid in universe:
            return eid
        for k, u in universe.items():
            if same_org(name, u["name"]):
                return k
        return None

    # ---- investor touches: key -> {company_id: sources}
    inv_touch: dict[str, dict] = {}

    def touch_inv(inv: dict, cid: str, sources: list[dict]):
        k = norm_key(inv["name"]) or inv["id"]
        t = inv_touch.setdefault(k, {"inv": inv, "companies": {}})
        prev = t["companies"].get(cid, [])
        t["companies"][cid] = merge_sources(prev, sources, cap=4)

    for c in list(port) + list(rivals.values()):
        for inv in c["investors"]:
            touch_inv(inv, c["id"], inv["sources"])
    # investor-side edges (catches rivals whose own record lacks the investor)
    for c in port:
        for inv in c["investors"]:
            e = inv_ents.get(inv["id"])
            if not e:
                continue
            for edge in e["out"].get("INVESTED_IN", []):
                cid = find_company(edge["id"], edge["name"])
                if cid and cid != c["id"]:
                    touch_inv(inv, cid, edge["sources"])
            for edge in e["out"].get("PARTICIPATES_IN_CORPORATE_EVENT", []):
                pass  # event participants are already covered from the issuer side

    # ---- person touches: person key -> {company_id: role}
    per_touch: dict[str, dict] = {}

    def touch_person(p: dict, cid: str, role: str, sources: list[dict], board: bool):
        k = kg.person_key(p["name"])
        t = per_touch.setdefault(k, {"person": p, "companies": {}})
        t["companies"].setdefault(cid, {"role": role, "sources": sources[:3], "board": board})

    for c in list(port) + list(rivals.values()):
        for p in c["people"]:
            touch_person(p, c["id"], p["role"], p["sources"], p["board"])
    for c in port:
        for p in c["people"]:
            e = persons.get(p["id"])
            if not e:
                continue
            p["other"] = []
            for rel, lst in e["out"].items():
                if rel in kg.PERSON_REL_SKIP:
                    continue
                for edge in lst:
                    if edge["type"] not in kg.COMPANY_TYPES or edge["id"] == c["id"] or same_org(
                            edge["name"], c["name"]):
                        continue
                    role = edge.get("role") or kg.ROLE_BY_REL.get(rel, rel.replace("_", " ").lower())
                    is_board = rel == "IS_BOARD_MEMBER_OF" or any(w in (role or "").lower() for w in kg.BOARD_WORDS)
                    p["other"].append({"id": edge["id"], "name": short_company(edge["name"]), "role": role,
                                       "rel": rel, "board": is_board})
                    cid = find_company(edge["id"], edge["name"])
                    if cid:
                        touch_person(p, cid, role, edge["sources"], is_board)

    # ---- shared_with annotations
    def names(cids, exclude):
        return [universe[x]["name"] for x in cids if x != exclude]

    for c in port:
        for inv in c["investors"]:
            t = inv_touch.get(norm_key(inv["name"]) or inv["id"])
            if t and len(t["companies"]) > 1:
                inv["shared_with"] = names(t["companies"], c["id"])
        for p in c["people"]:
            t = per_touch.get(kg.person_key(p["name"]))
            if t and len(t["companies"]) > 1:
                p["shared_with"] = names(t["companies"], c["id"])

    items: list[dict] = []
    signals: list[dict] = []
    port_by_id = {c["id"]: c for c in port}

    def cref(cid):
        u = universe[cid]
        return {"id": cid, "name": u["name"], "type": "Company"}

    # ---- investor overlaps
    for k, t in inv_touch.items():
        cids = list(t["companies"])
        if len(cids) < 2:
            continue
        inv = t["inv"]
        iref = {"id": inv["id"], "name": inv["name"], "type": inv.get("type", "Investor")}
        ps = [x for x in cids if universe[x]["kind"] == "portfolio"]
        rs = [x for x in cids if universe[x]["kind"] == "rival"]
        if not ps:
            continue
        if rs:
            for r in rs:
                direct = [p for p in ps if p in rival_of.get(r, [])]
                p = direct[0] if direct else ps[0]
                rp = direct[0] if direct else rival_of[r][0]
                sev = "high" if direct else "medium"
                rel = f"rival of {universe[rp]['name']}"
                if direct:
                    title = f"{inv['name']} backs {universe[p]['name']} and its rival {universe[r]['name']}"
                else:
                    title = (f"{inv['name']} backs {universe[p]['name']} and {universe[r]['name']}, "
                             f"a rival of {universe[rp]['name']}")
                srcs = merge_sources(t["companies"][p], t["companies"][r], cap=6)
                body = (f"Cala lists {inv['name']} as an investor in both {universe[p]['name']} and "
                        f"{universe[r]['name']}. Board access or information rights at a direct competitor "
                        f"are worth checking.")
                items.append({
                    "id": _id("inv", k, r), "kind": "overlap_investor", "category": "Overlaps", "severity": sev,
                    "status": "confirmed", "title": title, "body": body,
                    "date": _latest(srcs), "company": cref(p),
                    "subject": {**cref(r), "relation": rel}, "investor": iref,
                    "sources": srcs, "actions": ["draft_note"]})
                signals.append({"kind": "Shared investor", "text": title,
                                "entities": [iref, cref(p), cref(r)], "sources": srcs[:4], "severity": sev})
        if len(ps) > 1:
            text = f"{inv['name']} backs " + _join([universe[x]["name"] for x in ps])
            srcs = merge_sources(*[t["companies"][x] for x in ps], cap=6)
            signals.append({"kind": "Shared investor", "text": text,
                            "entities": [iref] + [cref(x) for x in ps], "sources": srcs[:4], "severity": "info"})

    # ---- people overlaps
    for k, t in per_touch.items():
        cids = list(t["companies"])
        if len(cids) < 2:
            continue
        p = t["person"]
        pref = {"id": p["id"], "name": p["name"], "type": "Person"}
        ps = [x for x in cids if universe[x]["kind"] == "portfolio"]
        rs = [x for x in cids if universe[x]["kind"] == "rival"]
        if not ps:
            continue
        board = any(v["board"] for v in t["companies"].values())
        for r in rs or []:
            direct = [x for x in ps if x in rival_of.get(r, [])]
            pc = direct[0] if direct else ps[0]
            rp = direct[0] if direct else rival_of[r][0]
            rrole = t["companies"][r]["role"]
            prole = t["companies"][pc]["role"]
            kind = "overlap_board" if board else "hiring"
            sev = "high" if (board and direct) else "medium"
            title = (f"{p['name']} ({prole}, {universe[pc]['name']}) also "
                     f"{_verb(rrole, t['companies'][r]['board'])} {universe[r]['name']}")
            srcs = merge_sources(t["companies"][pc]["sources"], t["companies"][r]["sources"])
            items.append({
                "id": _id("per", k, r), "kind": kind, "category": "Overlaps", "severity": sev,
                "status": "confirmed", "title": title,
                "body": f"Cala links {p['name']} to both {universe[pc]['name']} and {universe[r]['name']}"
                        f" ({'direct rival' if direct else 'rival of ' + universe[rp]['name']}).",
                "date": _latest(srcs), "company": cref(pc),
                "subject": {**cref(r), "relation": f"rival of {universe[rp]['name']}"}, "person": pref,
                "sources": srcs, "actions": ["draft_note"]})
            signals.append({"kind": "Board seat" if board else "Talent", "text": title,
                            "entities": [pref, cref(pc), cref(r)], "sources": srcs[:4], "severity": sev})
        if len(ps) > 1:
            text = f"{p['name']} sits across " + _join([universe[x]["name"] for x in ps])
            srcs = merge_sources(*[t["companies"][x]["sources"] for x in ps])
            signals.append({"kind": "Board seat" if board else "Talent", "text": text,
                            "entities": [pref] + [cref(x) for x in ps], "sources": srcs[:4], "severity": "info"})

    # ---- corporate events (funding, M&A) for portfolio and rivals
    seen_events = set()
    for c in list(port) + list(rivals.values()):
        is_port = c["id"] in port_by_id
        for ev in c["events"]:
            if ev["id"] in seen_events and ev["kind"] != "mna":
                continue
            age = months_ago(ev.get("date"))
            role = (ev.get("role") or "").upper()
            if ev["kind"] == "funding" and role in ("ISSUER", ""):
                if age is None or age > 36:
                    continue
                seen_events.add(ev["id"])
                label = event_label(ev, c["name"], role)
                amt = f" {ev['amount']}" if ev.get("amount") else ""
                if is_port:
                    title = f"{c['name']} raised{amt} ({label})" if label != "Funding round" else \
                        f"{c['name']} raised{amt or ' a new round'}"
                    sev = "info"
                    company, subject = cref(c["id"]), None
                else:
                    rp = rival_of[c["id"]][0]
                    title = f"Rival {c['name']} raised{amt}" + (f" ({label})" if label != "Funding round" else "")
                    sev = "medium" if age <= 12 else "low"
                    company = cref(rp)
                    subject = {**cref(c["id"]), "relation": f"rival of {universe[rp]['name']}"}
                inv_names = [short_company(p["name"]) for p in ev["participants"]
                             if (p.get("role") or "").upper() == "INVESTOR"][:4]
                body = ev.get("description") or ""
                if inv_names:
                    body = (body + " " if body else "") + "Investors: " + ", ".join(inv_names) + "."
                item = {"id": _id("fund", ev["id"]), "kind": "funding", "category": "Funding", "severity": sev,
                        "status": "confirmed", "title": title, "body": body.strip(), "date": ev.get("date"),
                        "company": company, "sources": ev["sources"], "actions": ["draft_note"]}
                if subject:
                    item["subject"] = subject
                items.append(item)
                if age <= 18:
                    signals.append({"kind": "Funding", "text": title,
                                    "entities": [cref(c["id"])], "sources": ev["sources"][:3],
                                    "severity": sev})
            elif ev["kind"] == "mna":
                if ev["id"] in seen_events or (age is not None and age > 36):
                    continue
                seen_events.add(ev["id"])
                parts = ev["participants"]
                acq = next((p for p in parts if (p.get("role") or "").upper() == "ACQUIRER"), None)
                tgt = next((p for p in parts if (p.get("role") or "").upper() == "TARGET"), None)
                acq_id = find_company(acq["id"], acq["name"]) if acq else None
                tgt_id = find_company(tgt["id"], tgt["name"]) if tgt else None
                an = short_company(acq["name"]) if acq else c["name"]
                tn = short_company(tgt["name"]) if tgt else None
                amt = f" for {ev['amount']}" if ev.get("amount") else ""
                verb = "agreed to acquire" if "expected" in (ev.get("description") or "").lower() else "acquired"
                title = f"{an} {verb} {tn}{amt}" if tn else f"{an}: M&A{amt}"
                # who does it concern?
                if tgt_id and universe[tgt_id]["kind"] == "rival":
                    rp = rival_of[tgt_id][0]
                    sev, company = "high" if (age or 0) <= 12 else "medium", cref(rp)
                    subject = {**cref(tgt_id), "relation": f"rival of {universe[rp]['name']}"}
                    if acq_id and universe[acq_id]["kind"] == "portfolio":
                        company = cref(acq_id)
                        sev = "medium"
                        title = f"{an} {verb} {tn}{amt}, one of its closest rivals"
                elif acq_id and universe[acq_id]["kind"] == "rival":
                    rp = rival_of[acq_id][0]
                    sev, company = ("medium" if (age or 99) <= 12 else "low"), cref(rp)
                    subject = {**cref(acq_id), "relation": f"rival of {universe[rp]['name']}"}
                    title = f"Rival {title}"
                elif is_port:
                    sev, company, subject = "info" if role == "ACQUIRER" else "high", cref(c["id"]), None
                else:
                    rp = rival_of.get(c["id"], [None])[0]
                    if not rp:
                        continue
                    sev, company = "low", cref(rp)
                    subject = {**cref(c["id"]), "relation": f"rival of {universe[rp]['name']}"}
                item = {"id": _id("mna", ev["id"]), "kind": "mna", "category": "Other", "severity": sev,
                        "status": "confirmed", "title": title, "body": ev.get("description") or "",
                        "date": ev.get("date"), "company": company, "sources": ev["sources"],
                        "actions": ["draft_note"]}
                if subject:
                    item["subject"] = subject
                items.append(item)
                ents = [cref(x) for x in (acq_id, tgt_id) if x]
                signals.append({"kind": "M&A", "text": title, "entities": ents or [company],
                                "sources": ev["sources"][:3], "severity": sev})

    # ---- screening (knowledge_search) findings
    for c in port:
        s = screens.get(c["id"])
        for f in (s or {}).get("findings", []):
            items.append(_finding_item(f, cref(c["id"]), None))
    for rid, s in rival_screens.items():
        if not s or rid not in rival_of:
            continue
        rp = rival_of[rid][0]
        for f in s.get("findings", [])[:3]:
            f2 = dict(f)
            f2["severity"] = "low" if f["severity"] != "high" else "medium"
            f2["title"] = f"Rival {universe[rid]['name']}: {f['title']}" if universe[rid]["name"].lower() not in \
                f["title"].lower() else f["title"]
            items.append(_finding_item(f2, cref(rp), {**cref(rid), "relation": f"rival of {universe[rp]['name']}"}))

    # dedupe ids, sort newest first
    uniq = {}
    for it in items:
        uniq.setdefault(it["id"], it)
    items = sorted(uniq.values(), key=lambda i: (i.get("date") or "0000", _sev_rank(i["severity"])), reverse=True)
    signals = _dedupe_signals(signals)

    need = sum(1 for i in items if i["severity"] in ("high", "medium") and (months_ago(i.get("date")) or 0) <= 12)
    n = len(port)
    summary = (f"{need} thing{'s' if need != 1 else ''} need{'s' if need == 1 else ''} a look across your {n} "
               f"compan{'ies' if n != 1 else 'y'}." if need else f"All quiet across your {n} companies.")

    # ---- perimeter view
    def pub_company(c):
        return {
            "id": c["id"], "name": c["name"], "description": c["description"], "website": c.get("website"),
            "hq": c.get("hq"), "founded": c.get("founded"), "industry": c.get("industry"),
            "rivals": [{"id": r["id"], "name": rivals[r["id"]]["name"], "type": "Company",
                        "sub": r.get("sub"), "confidence": r.get("confidence")}
                       for r in c["rivals"] if r["id"] in rivals],
            "investors": [{k: v for k, v in {"id": i["id"], "name": i["name"], "type": i["type"], "sub": i["sub"],
                                             "shared_with": i.get("shared_with")}.items() if v is not None}
                          for i in c["investors"][:20]],
            "people": [{k: v for k, v in {"id": p["id"], "name": p["name"], "type": "Person", "role": p["role"],
                                          "sub": p["role"], "shared_with": p.get("shared_with")}.items()
                        if v is not None} for p in c["people"][:15]],
        }

    pub = [pub_company(c) for c in port]
    shown_rivals = {r["id"] for c in pub for r in c["rivals"]}
    shown_inv = {norm_key(i["name"]) for c in pub for i in c["investors"]}
    shown_people = {p["id"] for c in pub for p in c["people"]}
    countries = {c.get("country") for c in port if c.get("country")} | {
        rivals[r]["country"] for r in shown_rivals if rivals[r].get("country")}
    facts = sum(c["facts_count"] + len(c["events"]) for c in list(port) + list(rivals.values()))
    stats = {"rivals": len(shown_rivals), "investors": len(shown_inv), "people": len(shown_people),
             "countries": len(countries), "entities": len(pub) + len(shown_rivals) + len(shown_inv) + len(shown_people),
             "facts": facts}

    return {
        "perimeter": {"companies": pub, "stats": stats, "signals": signals},
        "feed": {"summary": summary, "items": items},
        "portfolio": [_company_pub(c) for c in port],
        "rivals_index": {rid: {"name": universe[rid]["name"], "of": [universe[x]["name"] for x in v]}
                         for rid, v in rival_of.items()},
    }


def _company_pub(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "name", "description", "website", "hq", "founded")}


def _finding_item(f: dict, company: dict, subject: dict | None) -> dict:
    kind = {"regulatory": "regulatory", "legal": "legal", "sanctions": "regulatory", "news": "news"}[f["category"]]
    it = {"id": _id("scr", company["id"], subject["id"] if subject else "", f["title"]), "kind": kind,
          "category": "Risk", "severity": f["severity"], "status": "reported", "title": f["title"],
          "body": f["body"], "date": f.get("date"), "company": company, "sources": f["sources"],
          "actions": ["draft_note"]}
    if subject:
        it["subject"] = subject
    return it


def _sev_rank(s: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "info": 0}.get(s, 0)


def _latest(srcs: list[dict]) -> str | None:
    ds = sorted((s["date"] for s in srcs if s.get("date")), reverse=True)
    return ds[0] if ds else None


def _join(xs: list[str]) -> str:
    xs = list(dict.fromkeys(xs))
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _verb(role: str, board: bool) -> str:
    low = (role or "").lower()
    if board or "board" in low or "director" in low:
        return "sits on the board of"
    if "found" in low:
        return "co-founded"
    if low in ("ceo", "cto", "coo", "cfo", "cco", "president", "chair") or low.startswith("chief"):
        return f"is {role} of"
    if "invest" in low:
        return "invested in"
    return "works at"


def _dedupe_signals(signals: list[dict]) -> list[dict]:
    seen, out = set(), []
    for s in sorted(signals, key=lambda s: -_sev_rank(s.get("severity", "info"))):
        if s["text"] in seen:
            continue
        seen.add(s["text"])
        out.append(s)
    return out[:40]
