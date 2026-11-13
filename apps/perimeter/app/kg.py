"""Cala knowledge-graph helpers: entity normalisation, resolution, events, rivals, screening."""
from __future__ import annotations

import asyncio
import difflib
import html
import re
import unicodedata
from datetime import date
from typing import Any

from .cala import CalaError, cala

COMPANY_TYPES = {"Company", "Organization", "NonprofitOrganization", "HealthcareEstablishment",
                 "EducationalInstitution", "ResearchInstitution"}
EVENT_TYPES = {"PrivateCompanyFundingRound", "CorporateEvent", "FundingRound", "RegulatoryEvent"}
EVENT_PROPS = ["description", "event_date", "transaction_value", "transaction_value_units",
               "event_type", "round_type"]

ROLE_BY_REL = {
    "FOUNDED": "Founder", "IS_CEO_OF": "CEO", "IS_CTO_OF": "CTO", "IS_COO_OF": "COO", "IS_CFO_OF": "CFO",
    "IS_CCO_OF": "CCO", "IS_BOARD_MEMBER_OF": "Board member", "IS_EXECUTIVE_OF": "Executive",
    "IS_CHAIRMAN_OF": "Chair", "IS_PRESIDENT_OF": "President", "IS_CONTROL_PERSON_OF": "Controlling person",
    "IS_BENEFICIARY_OWNER_OF": "Beneficial owner", "WORKS_AT": "Works at", "IS_MEMBER_OF": "Member",
}
BOARD_WORDS = ("board", "chair", "director", "supervisory")
PERSON_REL_SKIP = {"HAS_NATIONALITY"}

TODAY = date.today()


# --------------------------------------------------------------------------- utils
def src(s: dict) -> dict:
    url = s.get("document") or s.get("url") or None
    d = s.get("date") or None
    if d and (d[:4] < "2005" or d[:4] > str(TODAY.year)):
        d = None  # placeholder dates like 2000-01-01 carry no information
    return {"name": (s.get("name") or (url or "Cala")).strip()[:160], "url": url or None, "date": d}


def merge_sources(*lists: list[dict], cap: int = 6) -> list[dict]:
    out, seen = [], set()
    for lst in lists:
        for s in lst or []:
            k = s.get("url") or s.get("name")
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
    # prefer sources with a URL, newest first
    out.sort(key=lambda s: (s.get("url") is None, "" if not s.get("date") else "~" + s["date"]), reverse=False)
    out.sort(key=lambda s: s.get("date") or "", reverse=True)
    out.sort(key=lambda s: s.get("url") is None)
    return out[:cap]


_LEGAL = {"llc", "lp", "llp", "ltd", "limited", "gmbh", "inc", "incorporated", "sa", "sas", "bv", "nv", "plc",
          "co", "kg", "ag", "ab", "oy", "as", "spa", "srl", "corp", "corporation", "company", "the", "and",
          "holdings", "holding", "group", "management", "affiliated", "investment", "investments", "funds", "fund",
          "advisors", "advisers", "partnership", "lllp", "pte", "pty", "sarl", "se", "geschlossene",
          "mbh", "ug", "collectively", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "l", "p"}
_GENERIC = {"capital", "ventures", "venture", "partners", "vc"}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_tokens(name: str) -> list[str]:
    s = strip_accents(name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"(?<![a-z])([a-z])\.([a-z])\.?(?![a-z])", lambda m: m.group(1) + m.group(2), s)  # n.v. -> nv
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t not in _LEGAL and not t.isdigit()]
    return toks


def norm_key(name: str) -> str:
    toks = norm_tokens(name)
    core = [t for t in toks if t not in _GENERIC] or toks
    return " ".join(core[:3])


def same_org(a: str, b: str) -> bool:
    ka, kb = norm_key(a), norm_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = ka.split(), kb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # token prefix ("tcv" vs "technology crossover"? no; "index" vs "index ventures") – need >=4 chars
    return len(" ".join(short)) >= 4 and long_[: len(short)] == short


def clean_name(name: str) -> str:
    """Display name: drop trailing parentheticals and boilerplate, fix SHOUTING."""
    n = name or ""
    m = re.search(r'\(collectively\s+"?([^")]+)"?\)', n)
    if m:
        return m.group(1).strip()
    n = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()
    n = re.sub(r"\s+affiliated investment funds?$", "", n, flags=re.I)
    if n.isupper() and len(n.replace(" ", "")) > 4:
        words = []
        for w in n.split():
            lw = w.lower().strip(".,").replace(".", "")
            if lw in {"llc", "lp", "llp", "ltd", "gmbh", "inc", "sa", "sas", "bv", "nv", "plc", "ag", "ab"}:
                words.append(w.upper() if lw in {"llc", "lp", "llp", "bv", "nv", "plc", "sa", "sas", "ag", "ab"}
                             else w.capitalize())
            else:
                words.append(w.capitalize())
        n = " ".join(words)
    return n.strip() or name


def short_company(name: str) -> str:
    """'Revolut Ltd' -> 'Revolut' for prose."""
    n = clean_name(name)
    n2 = re.sub(r"[,\s]+(Ltd\.?|Limited|LLC|L\.?P\.?|LLP|GmbH|Inc\.?|S\.?A\.?S?\.?|B\.?V\.?|N\.?V\.?|PLC\.?|AG|AB|SE|S\.r\.l\.?|S\.p\.A\.?|SRL|SpA)$",
                "", n, flags=re.I)
    return n2.strip() or n


def similarity(a: str, b: str) -> float:
    ka, kb = " ".join(norm_tokens(a)), " ".join(norm_tokens(b))
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    return difflib.SequenceMatcher(None, ka, kb).ratio()


def fmt_amount(value: Any, units: str | None) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    u = (units or "").strip()
    mult = 1.0
    if re.search(r"\bbn\b|billion", u, re.I):
        mult, u = 1e9, re.sub(r"\s*\b(billion|bn)\b\s*", " ", u, flags=re.I).strip()
    elif re.search(r"\bm\b|\bmn\b|million", u, re.I):
        mult, u = 1e6, re.sub(r"\s*\b(million|mn|m)\b\s*", " ", u, flags=re.I).strip()
    elif v < 10000:
        mult = 1e6  # Cala sometimes stores deal values in millions without saying so
    v *= mult
    units = u
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get((units or "").upper(), "")
    suffix = "" if sym else f" {units}" if units else ""
    if v >= 1e9:
        s = f"{v / 1e9:.2f}".rstrip("0").rstrip(".") + "bn"
    elif v >= 1e6:
        s = f"{v / 1e6:.1f}".rstrip("0").rstrip(".") + "M"
    elif v >= 1e3:
        s = f"{v / 1e3:.0f}k"
    else:
        s = f"{v:.0f}"
    return f"{sym}{s}{suffix}"


def trim_text(s: str | None, n: int) -> str | None:
    """Shorten to n chars at a sentence or word boundary, never mid-word."""
    s = (s or "").strip()
    if len(s) <= n:
        return s or None
    cut = s[:n]
    m = re.search(r"^(.{40,})[.;!?](?:\s|$)", cut)
    if m:
        return m.group(1) + "."
    cut = re.sub(r"(?:[\s,;:—–-]+(?:and|or|with|the|a|an|of|to|for|in))+$", "", cut.rsplit(" ", 1)[0])
    return cut.rstrip(",;:—–- ") + "…"


def months_ago(d: str | None) -> float | None:
    if not d:
        return None
    try:
        parts = [int(x) for x in d[:10].split("-")] + [1, 1]
        y, m, dd = parts[:3]
        return (TODAY - date(y, m, dd)).days / 30.44
    except Exception:
        return None


def title_industry(s: str) -> str:
    s = s.replace("_", " ").lower()
    return {"fintech": "Fintech"}.get(s, s[:1].upper() + s[1:])


# --------------------------------------------------------------------------- entities
def _edge(x: dict) -> dict:
    p = x.get("properties") or {}
    return {"id": x.get("id"), "name": x.get("name") or "", "type": x.get("entity_type") or "Entity",
            "role": p.get("role"), "date": p.get("event_date"),
            "sources": [src(s) for s in p.get("sources") or []]}


# Superset used when no introspection is cached: Cala ignores unknown properties/relationships, so one
# retrieval replaces introspection + retrieval (Cala rate-limits at roughly 20 calls/minute).
_ROLE_RELS = ["FOUNDED", "WORKS_AT", "IS_CEO_OF", "IS_CTO_OF", "IS_COO_OF", "IS_CFO_OF", "IS_CCO_OF",
              "IS_BOARD_MEMBER_OF", "IS_EXECUTIVE_OF", "IS_CHAIRMAN_OF", "IS_PRESIDENT_OF", "IS_MEMBER_OF",
              "IS_CONTROL_PERSON_OF", "IS_BENEFICIARY_OWNER_OF", "INVESTED_IN"]
SUPER_PROPS = ["name", "legal_name", "aliases", "website", "lei", "description", "registered_address",
               "headquarters_address", "founding_date", "birth_date"]
SUPER_OUT = ["IS_REGISTERED_IN", "HAS_HEADQUARTERS_IN", "OPERATES_IN_INDUSTRY", "PARTICIPATES_IN_CORPORATE_EVENT",
             "HAS_PRESENCE_IN", "IS_DIRECT_PARENT_OF", "IS_ULTIMATE_PARENT_OF", "LISTED_ON", "HAS_NATIONALITY",
             *_ROLE_RELS]
SUPER_IN = [*_ROLE_RELS, "IS_DIRECT_PARENT_OF", "IS_ULTIMATE_PARENT_OF", "PARTICIPATES_IN_CORPORATE_EVENT"]


async def fetch_entity(eid: str, limit: int = 30) -> dict:
    intro = cala.cached("entity_introspection", {"entity_id": eid})
    if intro is not None:
        props = [p for p in intro.get("properties") or [] if p != "id"]
        rels = intro.get("relationships") or {}
        out_rels = {k: limit for k in rels.get("outgoing") or []}
        in_rels = {k: limit for k in rels.get("incoming") or []}
    else:
        props, out_rels, in_rels = SUPER_PROPS, {k: limit for k in SUPER_OUT}, {k: limit for k in SUPER_IN}
    r = await cala.retrieve(eid, props, out_rels or None, in_rels or None)
    ent = {
        "id": r.get("id") or eid, "name": r.get("name") or "", "type": r.get("entity_type") or "Entity",
        "description": r.get("description") or "",
        "props": {}, "out": {}, "inc": {},
    }
    for k, v in (r.get("properties") or {}).items():
        if isinstance(v, dict) and "value" in v and v["value"] not in (None, "", []):
            ent["props"][k] = {"value": v["value"], "sources": [src(s) for s in v.get("sources") or []]}
    for d, key in (("outgoing", "out"), ("incoming", "inc")):
        for rel, lst in ((r.get("relationships") or {}).get(d) or {}).items():
            ent[key][rel] = [_edge(x) for x in lst or [] if x.get("id")]
    return ent


async def safe_entity(eid: str, limit: int = 30) -> dict | None:
    try:
        return await fetch_entity(eid, limit)
    except Exception:
        return None


def pval(ent: dict, k: str) -> Any:
    v = ent.get("props", {}).get(k)
    return v["value"] if v else None


def psrc(ent: dict, k: str) -> list[dict]:
    v = ent.get("props", {}).get(k)
    return v["sources"] if v else []


def entity_ref(e: dict, sub: str | None = None) -> dict:
    t = e.get("type") or "Entity"
    if t in COMPANY_TYPES:
        t = "Company"
    ref = {"id": e.get("id"), "name": clean_name(e.get("name") or ""), "type": t}
    if sub:
        ref["sub"] = sub
    return ref


def company_basics(ent: dict) -> dict:
    """Contract `Company` shape + extras."""
    out = ent.get("out", {})
    country = next((e["name"] for e in out.get("HAS_HEADQUARTERS_IN", []) if e["type"] == "Country"), None)
    country = country or next((e["name"] for e in out.get("IS_REGISTERED_IN", []) if e["type"] == "Country"), None)
    city = next((e["name"] for e in out.get("HAS_HEADQUARTERS_IN", []) if e["type"] == "Municipality"), None)
    addr = pval(ent, "headquarters_address") or ""
    parts = [p.strip() for p in str(addr).split(",") if p.strip()]
    if not city and len(parts) >= 3 and not re.search(r"\d", parts[1]):
        city = parts[1].title() if parts[1].isupper() else parts[1]
    hq = ", ".join(x for x in (city, country) if x) or None
    founded = pval(ent, "founding_date")
    inds = [title_industry(e["name"]) for e in out.get("OPERATES_IN_INDUSTRY", [])]
    rank = ["fintech", "banking", "insurance", "healthcare", "biotechnology", "energy", "software and services"]
    pref = sorted(inds, key=lambda i: rank.index(i.lower()) if i.lower() in rank else 50)
    website = pval(ent, "website")
    c = {"id": ent["id"], "name": short_company(ent["name"]), "description": ent.get("description") or "",
         "website": website, "hq": hq, "founded": str(founded)[:4] if founded else None,
         "industry": pref[0] if pref else None, "country": country, "industries": inds}
    return c


# --------------------------------------------------------------------------- resolution
async def richness(eid: str) -> int:
    try:
        intro = await cala.introspect(eid)
    except Exception:
        return -1
    rels = intro.get("relationships") or {}
    out, inc = rels.get("outgoing") or [], rels.get("incoming") or []
    score = len(intro.get("properties") or []) + 2 * (len(out) + len(inc))
    score += 6 * ("PARTICIPATES_IN_CORPORATE_EVENT" in out) + 4 * ("INVESTED_IN" in inc) + 3 * ("FOUNDED" in inc)
    return score


async def search_companies(name: str) -> list[dict]:
    try:
        res = await cala.search(name, ["Company", "Organization"])
    except CalaError:
        res = []
    if not res:
        try:
            res = await cala.search(name)
        except CalaError:
            res = []
    out = []
    for e in res:
        if e.get("entity_type") in COMPANY_TYPES:
            out.append(e)
    return out


async def resolve_company(name: str, hint_ids: list[str] | None = None) -> tuple[dict | None, list[dict], float]:
    """Return (best, candidates, confidence).

    Cala's own entity link (hint_ids, from knowledge_query) wins. Otherwise exact normalised-name matches are
    preferred, and among those the richest record (most properties/relationships) is chosen.
    """
    if hint_ids:  # Cala already linked the name to an entity: trust it, no extra calls
        return {"id": hint_ids[0], "name": name}, [], 0.95
    cands = await search_companies(name)
    scored = sorted(((similarity(name, c.get("name", "")), c) for c in cands), key=lambda t: -t[0])
    exact = [c for s, c in scored if s >= 0.999][:4]
    top = exact or [c for s, c in scored if s >= 0.75][:2]
    if not top:
        return None, [c for _, c in scored[:5]], 0.0
    if len(top) == 1:
        best = top[0]
    else:
        rich = await asyncio.gather(*[richness(c["id"]) for c in top])
        best = max(zip(top, rich), key=lambda t: t[1])[0]
    conf = next(s for s, c in scored if c["id"] == best["id"])
    return best, [c for _, c in scored[:5]], round(conf if exact else conf * 0.9, 2)


# --------------------------------------------------------------------------- events
def _event_kind(et: str, ent_type: str) -> str:
    et = (et or "").upper()
    if "MNA" in et or "ACQUI" in et or "MERGER" in et:
        return "mna"
    if "FINANC" in et or "FUNDING" in et or ent_type in ("PrivateCompanyFundingRound", "FundingRound"):
        return "funding"
    if "IPO" in et or "LISTING" in et:
        return "ipo"
    return "other"


async def fetch_event(edge: dict) -> dict | None:
    try:
        r = await cala.retrieve(edge["id"], EVENT_PROPS, None, {"PARTICIPATES_IN_CORPORATE_EVENT": 25})
    except Exception:
        return None
    props = r.get("properties") or {}

    def pv(k):
        v = props.get(k)
        return v.get("value") if isinstance(v, dict) else None

    srcs = []
    for v in props.values():
        if isinstance(v, dict):
            srcs.extend(src(s) for s in v.get("sources") or [])
    srcs = merge_sources(edge.get("sources") or [], srcs)
    et = pv("event_type") or r.get("name") or edge.get("name") or ""
    parts = [_edge(x) for x in ((r.get("relationships") or {}).get("incoming") or {}).get(
        "PARTICIPATES_IN_CORPORATE_EVENT", [])]
    return {
        "id": edge["id"], "kind": _event_kind(et, r.get("entity_type") or edge.get("type")),
        "event_type": et, "date": (pv("event_date") or edge.get("date") or None),
        "description": pv("description") or r.get("description") or "",
        "amount": fmt_amount(pv("transaction_value"), pv("transaction_value_units")),
        "round": pv("round_type"), "participants": parts, "sources": srcs,
    }


async def company_events(ent: dict, cap: int = 10) -> list[dict]:
    edges = [e for e in ent.get("out", {}).get("PARTICIPATES_IN_CORPORATE_EVENT", [])]
    edges.sort(key=lambda e: e.get("date") or "", reverse=True)
    evs = await asyncio.gather(*[fetch_event(e) for e in edges[:cap]])
    out = []
    for e, edge in zip(evs, edges[:cap]):
        if not e:
            continue
        e["role"] = edge.get("role")
        out.append(e)
    return out


def event_label(ev: dict, subject: str, role: str | None) -> str:
    """Human label for an event from the subject company's point of view."""
    role = (role or "").upper()
    if ev["kind"] == "funding":
        if role == "INVESTOR":
            issuer = next((p["name"] for p in ev["participants"] if (p.get("role") or "").upper() == "ISSUER"), None)
            return f"Invested in {short_company(issuer)}" if issuer else "Investment"
        rnd = ev.get("round") or _round_from_desc(ev.get("description", ""))
        return rnd or "Funding round"
    if ev["kind"] == "mna":
        other = [p for p in ev["participants"] if not same_org(p["name"], subject)]
        tgt = next((p["name"] for p in other if (p.get("role") or "").upper() == "TARGET"), None)
        acq = next((p["name"] for p in other if (p.get("role") or "").upper() == "ACQUIRER"), None)
        if role == "ACQUIRER":
            return f"Acquisition of {short_company(tgt)}" if tgt else "Acquisition"
        if role == "TARGET":
            return f"Acquired by {short_company(acq)}" if acq else "Acquired"
        return "M&A"
    return (ev.get("event_type") or "Event").replace("_", " ").capitalize()


def _round_from_desc(d: str) -> str | None:
    m = re.search(r"Round:\s*([^.]+)\.", d or "")
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------- people / investors
def people_of(ent: dict) -> list[dict]:
    """People attached to a company (incoming edges from Person entities)."""
    by_id: dict[str, dict] = {}
    for rel, lst in ent.get("inc", {}).items():
        for e in lst:
            if e["type"] != "Person" or rel == "INVESTED_IN":
                continue
            p = by_id.setdefault(e["id"], {"id": e["id"], "name": clean_name(e["name"]), "roles": [], "rels": set(),
                                           "sources": []})
            role = e.get("role") if rel in ("WORKS_AT", "IS_MEMBER_OF") and e.get("role") else ROLE_BY_REL.get(
                rel, rel.replace("IS_", "").replace("_OF", "").replace("_", " ").title())
            if role and role not in p["roles"]:
                p["roles"].append(role)
            p["rels"].add(rel)
            p["sources"] = merge_sources(p["sources"], e["sources"])
    # merge same-name duplicates
    merged: dict[str, dict] = {}
    for p in by_id.values():
        k = person_key(p["name"])
        if k in merged:
            m = merged[k]
            m["roles"] += [r for r in p["roles"] if r not in m["roles"]]
            m["rels"] |= p["rels"]
            m.setdefault("alt_ids", []).append(p["id"])
        else:
            merged[k] = p
    out = []
    for p in merged.values():
        p["role"] = _role_text(p["roles"])
        p["board"] = "IS_BOARD_MEMBER_OF" in p["rels"] or any(
            any(w in r.lower() for w in BOARD_WORDS) for r in p["roles"])
        p["rels"] = sorted(p["rels"])
        out.append(p)
    rank = lambda p: (0 if "FOUNDED" in p["rels"] or "IS_CEO_OF" in p["rels"] else 1 if p["board"] else 2)
    out.sort(key=rank)
    return out


def person_key(name: str) -> str:
    t = re.sub(r"[^a-z ]+", " ", strip_accents(name or "").lower()).split()
    return f"{t[0][:3]} {t[-1]}" if len(t) >= 2 else " ".join(t)  # "Nik"/"Nikolay Storonsky" merge


def _role_text(roles: list[str]) -> str:
    rich = [r for r in roles if r not in ROLE_BY_REL.values() and len(r) > 2]
    if rich:
        return rich[0]
    order = ["Founder", "CEO", "President", "Chair", "Board member", "CTO", "COO", "CFO", "CCO", "Executive"]
    rs = sorted(set(roles), key=lambda r: order.index(r) if r in order else 99)
    rs = [r for r in rs if r not in ("Works at", "Member")] or rs
    if "Founder" in rs and "CEO" in rs:
        rs = ["Founder & CEO"] + [r for r in rs if r not in ("Founder", "CEO")]
    return ", ".join(rs[:2]) or "Person"


def investors_of(ent: dict, events: list[dict]) -> list[dict]:
    """Investors from INVESTED_IN edges and INVESTOR participants of funding rounds."""
    me = ent["name"]
    out: dict[str, dict] = {}

    def add(e: dict, sources: list[dict], when: str | None, rnd: str | None, amount: str | None = None):
        if e["id"] == ent["id"] or same_org(e["name"], me):
            return
        k = norm_key(e["name"]) or e["id"]
        inv = out.get(k)
        if not inv:
            inv = out[k] = {"id": e["id"], "name": clean_name(e["name"]), "type": "Person" if e["type"] == "Person"
                            else "Investor", "ids": [e["id"]], "sources": [], "rounds": []}
        elif e["id"] not in inv["ids"]:
            inv["ids"].append(e["id"])
        inv["sources"] = merge_sources(inv["sources"], sources)
        if when or rnd:
            inv["rounds"].append({"date": when, "round": rnd, "amount": amount, "sources": sources[:2]})

    for e in ent.get("inc", {}).get("INVESTED_IN", []):
        add(e, e["sources"], None, None)
    for ev in events:
        if ev["kind"] != "funding" or (ev.get("role") or "").upper() not in ("ISSUER", ""):
            continue
        for p in ev["participants"]:
            if (p.get("role") or "").upper() == "INVESTOR":
                add(p, ev["sources"][:3], ev.get("date"), ev.get("round") or _round_from_desc(ev["description"]),
                    ev.get("amount"))
    res = list(out.values())
    for inv in res:
        ds = sorted(r["date"] for r in inv["rounds"] if r.get("date"))
        inv["sub"] = f"Investor since {ds[0][:4]}" if ds else "Investor"
        inv["first_date"] = ds[0] if ds else None
    res.sort(key=lambda i: (-len(i["rounds"]), i["name"]))
    return res


# --------------------------------------------------------------------------- rivals
async def find_rivals(c: dict, cap: int = 5) -> list[dict]:
    hint = ", ".join(x for x in (c.get("industry"), c.get("hq")) if x)
    q = f"closest competitors of {c['name']}" + (f" ({hint})" if hint else "")
    try:
        r = await cala.query(q)
    except Exception:
        return []
    results = (r or {}).get("results") or []
    ents = (r or {}).get("entities") or []
    names = []
    for row in results:
        n = row.get("name") or row.get("company") or row.get("company_name") or next(
            (v for v in row.values() if isinstance(v, str)), None)
        if not n:
            continue
        n = re.split(r"\s+/\s+|\s+\(", n)[0].strip()
        sub = row.get("key_overlap") or row.get("description") or row.get("overlap") or row.get("headquarters")
        names.append((n, sub if isinstance(sub, str) else None))

    async def one(n: str, sub: str | None):
        if same_org(n, c["name"]):
            return None
        hint_ids = [e["id"] for e in ents if e.get("entity_type") in COMPANY_TYPES and any(
            similarity(n, m) >= 0.85 for m in (e.get("mentions") or []) + [e.get("name", "")])]
        best, _, conf = await resolve_company(n, hint_ids[:1])
        if not best:
            return None
        return {"id": best["id"], "name": n, "sub": trim_text(sub, 120), "confidence": conf}

    picked = await asyncio.gather(*[one(n, s) for n, s in names[: cap + 3]])
    out, seen = [], {c["id"]}
    for p in picked:
        if p and p["id"] not in seen:
            seen.add(p["id"])
            out.append(p)
    return out[:cap]


# --------------------------------------------------------------------------- screening
ADVERSE = {
    "sanctions": ["sanction", "ofac", "asset freeze", "embargo", "designated"],
    "regulatory": ["fine", "fined", "penalt", "regulator", "aml", "anti-money", "money laundering", "enforcement",
                   "investigation", "probe", "licence", "license revoked", "restriction", "warning",
                   "supervis", "cease", "consent order", "watchdog", "breach of"],
    "legal": ["lawsuit", "sued", "suing", "court", "litigation", "class action", "settlement", "indict",
              "charged", "fraud", "criminal", "prosecut", "tribunal"],
    "news": ["data breach", "data exposure", "data leak", "leak", "hack", "outage", "layoff", "lay off", "job cuts", "redundanc",
             "insolven", "bankrupt", "administration", "write-down", "loss", "resign", "scandal", "exposed"],
}
NEGATIONS = ["no adverse", "no record", "no evidence", "no reported", "no known", "not found", "no information",
             "no specific", "no public", "no regulatory", "no sanctions", "not subject to", "no lawsuits",
             "did not find", "could not find", "no results", "none found", "no indication", "not been subject"]


def _classify(text: str) -> str | None:
    t = text.lower()
    for cat in ("sanctions", "regulatory", "legal", "news"):
        if any(w in t for w in ADVERSE[cat]):
            return cat
    return None


MONTHS = "january february march april may june july august september october november december".split()


def extract_date(text: str) -> str | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d\d)", t)
    if m:
        return f"{m.group(3)}-{MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d\d)", t)
    if m:
        return f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(" + "|".join(MONTHS) + r"|" + "|".join(x[:3] for x in MONTHS) + r")\.?\s+(20\d\d)", t)
    if m:
        mon = m.group(1)[:3]
        idx = [x[:3] for x in MONTHS].index(mon) + 1
        return f"{m.group(2)}-{idx:02d}-01"
    return None


def screen_query(name: str, hint: str | None = None) -> str:
    who = f"{name} ({hint})" if hint else name
    return f"Adverse news, regulatory actions, fines, lawsuits, investigations or sanctions involving {who} since 2025"


NEG_RE = re.compile(r"\bno (other |further |additional |major |specific |known |public |confirmed )*"
                    r"(adverse|sanction|lawsuit|regulatory|record|evidence|fine|enforcement|investigation|litigation"
                    r"|legal|reports?|news|issues?|findings?)|not (been )?(mentioned|identified|found|reported)"
                    r"|none (were |was )?(found|identified)", re.I)
_MONEY = re.compile(r"(£|€|\$)\s?[\d.,]+\s?(million|billion|bn|m|k)?", re.I)


def _ks_sources(refs: list[dict]) -> list[dict]:
    out = []
    for k in refs:
        for o in k.get("origins") or []:
            d = o.get("document") or {}
            s = o.get("source") or {}
            out.append({"name": d.get("name") or s.get("name") or "Source", "url": d.get("url") or s.get("url"),
                        "date": None})
    return merge_sources(out, cap=4)


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9€£$]{4,}", strip_accents(t.lower()))}


_STOP = set("that this with from were have been their which about after over into under they them also than such "
            "when other more most only said says will would could should against following since including "
            "company companies answer reported reports according these those there where while being across "
            "described noted notes states stated mentioned".split())


def _stems(t: str) -> set[str]:
    return {w[:5] for w in _words(t) if w not in _STOP and not w.isdigit()}


def _money(t: str) -> set[str]:
    return {m.group(0).replace(" ", "").lower() for m in _MONEY.finditer(t)}


def _domain(url: str | None) -> str | None:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else None


def _relevant_sources(step_refs: list[dict], all_ctx: list[dict], ent: str, title: str, body: str,
                      cap: int = 3) -> list[dict]:
    """Only sources that are actually about this finding.

    A source counts when its page title/URL names the company, or its snippet names the company and shares the
    finding's key terms (or amount). Pages whose title is about something else but whose snippet backs the finding
    are shown by domain, so the chip never reads as an unrelated headline.
    """
    key = _stems(title + " " + body[:500]) - {ent[:5]}
    money = _money(title + " " + body)
    step_ids = {id(k) for k in step_refs}
    cands = list(step_refs) + [k for k in all_ctx if id(k) not in step_ids]
    scored = []
    for k in cands:
        from_step = id(k) in step_ids
        snip = k.get("content") or ""
        ls = strip_accents(snip.lower())
        ov = len(_stems(snip) & key)
        snip_ok = ent in ls and (bool(money & _money(snip)) or ov >= (3 if from_step else 5))
        for o in k.get("origins") or []:
            d, s = o.get("document") or {}, o.get("source") or {}
            name = (d.get("name") or s.get("name") or "").strip()
            url = d.get("url") or s.get("url")
            hay = strip_accents(f"{name} {url or ''}".lower())
            title_ok = ent in hay and (from_step or snip_ok or len(_stems(name) & key) >= 1)
            if not (title_ok or snip_ok):
                continue
            disp = name if title_ok and name else (_domain(url) or s.get("name") or name)
            if not disp:
                continue
            scored.append((2 * title_ok + from_step + min(ov, 10) / 10, {"name": disp[:160], "url": url,
                                                                       "date": None}))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for _, s in scored:
        k = (s["url"] or s["name"], s["name"].lower()[:60])
        if k[0] in seen or k[1] in seen:
            continue
        seen.update(k)
        out.append(s)
    return out[:cap]


def _severity(cat: str, text: str) -> str:
    lt = text.lower()
    sev = {"sanctions": "high", "regulatory": "medium", "legal": "medium", "news": "low"}[cat]
    if cat == "legal" and any(w in lt for w in ("fraud", "criminal", "indict", "charged")):
        sev = "high"
    if cat == "regulatory" and re.search(r"(£|€|\$)\s?\d[\d.,]*\s?(million|billion|bn|m)\b", lt):
        sev = "high"
    return sev


# ---- headline writing: turn an LLM section heading / evidence sentence into a clean feed headline
_MON = "|".join(MONTHS + [m[:3] for m in MONTHS])
_DATE_PHRASE = re.compile(
    r"\s*,?\s*\b(?:(?:in|on|since|during|by|from|between|around|as of)\s+)?(?:(?:early|late|mid)[\s-]+)?"
    r"(?:(?:\d{1,2}\s+)?(?:" + _MON + r")\.?(?:\s+\d{1,2})?,?(?:\s*[-‐‑–—]\s*(?:\d{1,2}\s+)?(?:" + _MON + r")\.?)?"
    r"\s+20\d\d|(?:Q[1-4]|H[12])\s+20\d\d|20\d\d\s*[-‐‑–—]\s*(?:20\d\d|ongoing|present)|(?<=in )20\d\d)\b",
    re.I)
_INTRO = re.compile(r"^(?:the answer (?:states|reports|notes|mentions|describes|says)(?: that)?\s+|"
                    r"(?:reports|sources) (?:say|show|indicate) that\s+|according to [^,]+,\s+)", re.I)
_CLAUSE = re.compile(r"\s*(?:;|:|\s[—–]\s|\s-\s|,\s+(?=(?:which|who|whom|where|as|after|following|including|"
                     r"according|while|though|although|despite|but|amid|with|and\s+(?:is|was|has|had)|"
                     r"\w+ing)\b))", re.I)
_BAD_START = re.compile(r"^(?:this|these|that|those|it|its|they|the investigation|the fine|the case|the lawsuit|"
                        r"despite|because|since|no|none|although|however|both|the only|the provided|the facts|who|"
                        r"whom|which|background|the \w+ (?:article|report|analysis|entry|record)|"
                        r"an? \w+ (?:article|report)|and|but|or|also)\b",
                        re.I)


def _tidy(s: str) -> str:
    s = re.sub(r"\*+|_{2,}|`", "", s)
    s = re.sub(r"\s*\([^()]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r"[‐‑]", "-", s)
    return s


def headline(sentence: str, ent: str, limit: int = 100) -> str | None:
    """Shortest leading clause run of an evidence sentence that names the company, without dates/brackets."""
    s = _INTRO.sub("", _tidy(sentence))
    s = _tidy(_DATE_PHRASE.sub("", s))
    parts = _CLAUSE.split(s)
    out = ""
    for p in parts:
        out = f"{out}, {p}" if out else p
        if ent in strip_accents(out.lower()):
            break
    out = out.strip(" ,.;:—–-")
    if not out or ent not in strip_accents(out.lower()) or len(out) > limit or _BAD_START.match(out):
        return None
    if re.search(r"\b(?:no|not|never|without|dated)\b", out, re.I) or len(out.split()) < 4 \
            or out.count("(") != out.count(")") or out.count("“") != out.count("”") or out.count('"') % 2:
        return None
    return out[:1].upper() + out[1:]


def _sentence_case(topic: str, evidence: str) -> str:
    """'Customer Data Exposure Incident' -> 'customer data exposure incident'. Words the evidence capitalises
    mid-sentence (Italy, Google, Fifth Circuit), acronyms and CamelCase keep their case."""
    def fix(m):
        core = m.group(0)
        if core[:1].isupper() and core[1:].islower() and \
                not re.search(rf"[A-Za-z,;]\s+{re.escape(core)}\b", evidence):
            return core.lower()
        return core
    return re.sub(r"[A-Za-z]+", fix, topic)


def topic_headline(topic: str, short: str, evidence: str, cat: str | None) -> str:
    """Fallback when no evidence sentence works: the section heading turned into a sentence."""
    t = _tidy(_DATE_PHRASE.sub("", _tidy(topic)))
    t = re.sub(r"\s+[—–-]\s+", ": ", t).strip(" ,.;:—–-")
    t = _sentence_case(t, evidence)
    left, sep, right = t.partition(": ")
    if sep and right and len(left.split()) <= 4 and all(w[:1].isupper() for w in left.split()):
        t = f"{right} in {left}"  # "Lithuania: €3.5 million AML fine" -> "€3.5 million AML fine in Lithuania"
    if strip_accents(short.lower()) in strip_accents(t.lower()):
        return t[:1].upper() + t[1:]
    if re.match(r"^[A-Z][\w.&-]*\s+(?:imposes|fines|hits|orders|bans|sues|charges|opens|launches|probes|"
                r"restricts|sanctions|warns)\b", t):
        return f"{t} on {short}"  # "BaFin imposes new sanctions" -> "... on N26"
    if cat == "news":
        return f"{t[:1].upper() + t[1:]} at {short}"
    return f"{short} faces {t}"


def extract_date_p(text: str) -> str | None:
    """Like extract_date but keeps precision: 'YYYY-MM-DD', 'YYYY-MM' or None."""
    t = text.lower()
    if re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d\d)", t) or \
            re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d\d)", t):
        return extract_date(text)
    d = extract_date(text)
    return d[:7] if d else None


def parse_screen(res: dict, name: str) -> dict:
    """Conservative parse of a knowledge_search screening answer into findings.

    Prefers the answer's numbered sections ("### 1. Lithuania — EUR 3.5m AML fine"), each backed by the
    explainability steps that talk about it; falls back to the steps themselves. Anything phrased as a
    negative ("no other fines…"), not about the company, or without a matching source is dropped.
    """
    content = (res or {}).get("content") or ""
    ctx = {k["id"]: k for k in (res or {}).get("context") or [] if k.get("id")}
    all_ctx = list(ctx.values())
    steps = [st for st in (res or {}).get("explainability") or [] if st.get("content")]
    first = (norm_tokens(name) or [""])[0]
    short = short_company(name).split(" ")[0] if first else name
    if first and strip_accents(short.lower()) != first:
        short = short_company(name)
    cands = []  # (heading, body, refs, evidence sentences, from_sections)
    secs = re.split(r"^#{2,4}\s*\d+\.\s*", content, flags=re.M)[1:]
    if secs:
        for sec in secs:
            title, _, body = sec.partition("\n")
            body = re.split(r"^#{1,4}\s", body, flags=re.M)[0]
            body = re.sub(r"\*+|^[-*]\s+", "", body, flags=re.M).strip()
            title = re.sub(r"\*+", "", title).strip()
            if NEG_RE.search(title) or title.lower().startswith("no "):
                continue
            tw = _words(title + " " + body[:600])
            ts = _stems(title)
            tm = _money(title + " " + body)
            refs, ev = [], []
            for st in steps:
                sm = _money(st["content"])
                ov = len(_words(st["content"]) & tw)
                if (tm & sm) or ov >= 6:
                    refs += [ctx[r] for r in st.get("references") or [] if r in ctx]
                    ev.append((3 * len(_stems(st["content"]) & ts) + ov + 4 * bool(tm & sm), st["content"]))
            if not refs and len(secs) == 1:
                refs = [ctx[r] for st in steps for r in st.get("references") or [] if r in ctx]
            sents = re.split(r"(?<=[.!?])\s+", body.replace("\n", " "))
            ev += [(3 * len(_stems(x) & ts) + 2 - i, x) for i, x in enumerate(sents[:3])]
            ev = [x for _, x in sorted(ev, key=lambda x: -x[0])]
            cands.append((title, " ".join(sents[:3]).strip(), refs, ev, True))
    elif not NEG_RE.search(content[:900]):
        seen_money: set[str] = set()
        for st in steps:
            body = st["content"].strip()
            money = _money(body)
            if money and money & seen_money:
                continue
            seen_money |= money
            cands.append(("", body, [ctx[r] for r in st.get("references") or [] if r in ctx], [body], False))

    findings, seen_titles = [], set()
    for heading, body, refs, ev, from_sec in cands:
        heading_h = html.unescape(heading)
        body = html.unescape(body)
        text = f"{heading_h}. {body}"
        lt = strip_accents(text.lower())
        if from_sec and NEG_RE.search(heading_h):
            continue
        if not from_sec and re.search(r"\b(no|not|without|only positive)\b", body, re.I):
            continue
        if first and first not in lt:
            continue
        hs = _stems(heading_h) - {first[:5]}
        need = max(1, (len(hs) + 1) // 2)
        lines = []
        for x in ev:
            h = headline(html.unescape(x), first)
            # an evidence line must stay on the section's topic; it reads best when the company is the subject
            if h and (not from_sec or not hs or len(_stems(h) & hs) >= need):
                lines.append((not strip_accents(h.lower()).startswith(first), len(lines), h))
        title = min(lines)[2] if lines else None
        if not title:
            if not from_sec:
                continue
            title = topic_headline(heading_h, short, " ".join([body, *ev]), _classify(heading_h))
        # classify on the cleaned headline first: a step only *mentioning* compliance is not a finding
        cat = _classify(heading_h) or _classify(title) or (_classify(text) if from_sec else None)
        if not cat:
            continue
        sources = _relevant_sources(refs, all_ctx, first, heading_h or title, body) if first else _ks_sources(refs)
        if not sources:
            continue  # unsourced (or only off-topic sources): drop rather than mis-cite
        when = extract_date_p(body) or extract_date_p(heading_h)
        if not when:
            m = re.search(r"\((?:[^)]*\D)?(20\d\d)\)", heading_h)
            when = m.group(1) if m else None
        if when and when[:7] > TODAY.isoformat()[:7]:
            when = None
        sev = _severity(cat, text)
        age = months_ago(when)
        if age is not None and age > 24:
            continue
        if age is not None and age > 18 and sev == "medium":
            sev = "low"
        key = norm_key(title)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        sents = re.split(r"(?<=[.!?])\s+", _tidy(body))
        clean_body = " ".join(sents[:3]).strip()
        findings.append({"severity": sev, "status": "reported", "category": cat, "title": title,
                         "body": clean_body[:600], "date": when, "sources": sources})
    sanc = [f for f in findings if f["category"] == "sanctions"]
    # "screened" sources shown on a clear result must at least be about the company
    about = [k for k in all_ctx if first and first in strip_accents((k.get("content") or "").lower())]
    all_src = _ks_sources(about[:8])
    return {"findings": findings, "screened": len(ctx),
            "sanctions": {"clear": not sanc, "screened": len(ctx),
                          "text": (f"Possible sanctions exposure reported across {len(ctx)} sources" if sanc else
                                   f"No sanctions matches across {len(ctx)} screened sources"),
                          "sources": merge_sources(*[f["sources"] for f in sanc]) if sanc else all_src[:3]}}


async def screen(name: str, hint: str | None = None, only_cached: bool = False) -> dict | None:
    args = {"input": screen_query(name, hint)}
    if only_cached:
        res = cala.cached("knowledge_search", args)
        if res is None:
            return None
    else:
        try:
            res = await cala.call("knowledge_search", args)
        except Exception:
            return None
    return parse_screen(res, name)
