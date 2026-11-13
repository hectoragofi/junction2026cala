"""Cala knowledge-graph helpers: entity normalisation, resolution, events, rivals, screening."""
from __future__ import annotations

import asyncio
import difflib
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
    return {"name": (s.get("name") or (url or "Cala")).strip()[:160], "url": url or None,
            "date": (s.get("date") or None)}


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
    if n.isupper() and len(n) > 4:
        words = []
        for w in n.split():
            lw = w.lower().strip(".,")
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
    n2 = re.sub(r"[,\s]+(Ltd\.?|Limited|LLC|L\.?P\.?|LLP|GmbH|Inc\.?|S\.?A\.?S?\.?|B\.?V\.?|N\.?V\.?|PLC\.?|AG|AB|SE)$",
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
    if re.search(r"bn|billion", u, re.I):
        mult, u = 1e9, re.sub(r"\s*(bn|billion)\s*", " ", u, flags=re.I).strip()
    elif re.search(r"m|mn|million", u, re.I):
        mult, u = 1e6, re.sub(r"\s*(mn|m|million)\s*", " ", u, flags=re.I).strip()
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


def months_ago(d: str | None) -> float | None:
    if not d:
        return None
    try:
        y, m, dd = (int(x) for x in d[:10].split("-"))
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


async def fetch_entity(eid: str, limit: int = 30) -> dict:
    intro = await cala.introspect(eid)
    props = [p for p in intro.get("properties") or [] if p != "id"]
    rels = intro.get("relationships") or {}
    out_rels = {k: limit for k in rels.get("outgoing") or []}
    in_rels = {k: limit for k in rels.get("incoming") or []}
    r = await cala.retrieve(eid, props, out_rels or None, in_rels or None)
    ent = {
        "id": r.get("id") or eid, "name": r.get("name") or "", "type": r.get("entity_type") or "Entity",
        "description": r.get("description") or "",
        "props": {}, "out": {}, "inc": {},
    }
    for k, v in (r.get("properties") or {}).items():
        if isinstance(v, dict) and "value" in v:
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
    return len(intro.get("properties") or []) + 2 * (len(rels.get("outgoing") or []) + len(rels.get("incoming") or []))


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
    cands = await search_companies(name)
    scored = sorted(((similarity(name, c.get("name", "")), c) for c in cands), key=lambda t: -t[0])
    if hint_ids:
        h = hint_ids[0]
        best = next((c for _, c in scored if c["id"] == h), {"id": h, "name": name})
        return best, [c for _, c in scored[:5]], 0.95
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
            p = by_id.setdefault(e["id"], {"id": e["id"], "name": e["name"], "roles": [], "rels": set(),
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
    return f"{t[0]} {t[-1]}" if len(t) >= 2 else " ".join(t)


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

    def add(e: dict, sources: list[dict], when: str | None, rnd: str | None):
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
            inv["rounds"].append({"date": when, "round": rnd})

    for e in ent.get("inc", {}).get("INVESTED_IN", []):
        add(e, e["sources"], None, None)
    for ev in events:
        if ev["kind"] != "funding" or (ev.get("role") or "").upper() not in ("ISSUER", ""):
            continue
        for p in ev["participants"]:
            if (p.get("role") or "").upper() == "INVESTOR":
                add(p, ev["sources"][:3], ev.get("date"), ev.get("round") or _round_from_desc(ev["description"]))
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
        return {"id": best["id"], "name": n, "sub": (sub or "")[:120] or None, "confidence": conf}

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
    "news": ["data breach", "data exposure", "hack", "outage", "layoff", "lay off", "job cuts", "redundanc",
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


def parse_screen(res: dict, name: str) -> dict:
    """Conservative parse of a knowledge_search screening answer into findings."""
    content = (res or {}).get("content") or ""
    ctx = {k["id"]: k for k in (res or {}).get("context") or [] if k.get("id")}
    steps = (res or {}).get("explainability") or []
    heads = re.findall(r"^#{2,4}\s*\d+\.\s*(.+)$", content, flags=re.M)
    first = norm_tokens(name)[:1]
    findings = []
    low_content = content.lower()
    nothing = any(n in low_content[:600] for n in NEGATIONS) and not heads
    for i, st in enumerate(steps):
        body = (st.get("content") or "").strip()
        lb = body.lower()
        if not body or any(n in lb for n in NEGATIONS):
            continue
        if first and first[0] not in strip_accents(lb):
            continue
        cat = _classify(body)
        if not cat:
            continue
        refs = [ctx[r] for r in st.get("references") or [] if r in ctx]
        sources = []
        for k in refs:
            for o in k.get("origins") or []:
                d = o.get("document") or {}
                s = o.get("source") or {}
                sources.append({"name": d.get("name") or s.get("name") or "Source",
                                "url": d.get("url") or s.get("url"), "date": None})
        sources = merge_sources(sources, cap=4)
        if not sources:
            continue  # unsourced claims are dropped
        title = heads[i] if len(heads) == len(steps) else _short_title(body)
        title = re.sub(r"\*+", "", title).strip()
        when = extract_date(title) or extract_date(body) or extract_date(" ".join(k.get("content", "")[:400]
                                                                                for k in refs[:1]))
        sev = {"sanctions": "high", "regulatory": "medium", "legal": "medium", "news": "low"}[cat]
        if cat == "legal" and any(w in lb for w in ("fraud", "criminal", "indict", "charged")):
            sev = "high"
        if cat == "regulatory" and re.search(r"(£|€|\$)\s?\d{2,}\s?(m|million|bn|billion)", lb):
            sev = "high"
        age = months_ago(when)
        if age is not None and age > 24:
            continue
        if age is not None and age > 12 and sev == "medium":
            sev = "low"
        findings.append({"severity": sev, "status": "reported", "category": cat, "title": title[:110],
                         "body": body, "date": when, "sources": sources})
    if nothing:
        findings = []
    sanc = [f for f in findings if f["category"] == "sanctions"]
    all_src = []
    for k in list(ctx.values())[:8]:
        for o in k.get("origins") or []:
            d = o.get("document") or {}
            all_src.append({"name": d.get("name") or "Source", "url": d.get("url"), "date": None})
    return {"findings": findings, "screened": len(ctx),
            "sanctions": {"clear": not sanc, "screened": len(ctx),
                          "text": (f"Possible sanctions exposure reported across {len(ctx)} sources" if sanc else
                                   f"No sanctions matches across {len(ctx)} screened sources"),
                          "sources": merge_sources(*[f["sources"] for f in sanc]) if sanc else merge_sources(
                              all_src, cap=3)}}


def _short_title(body: str) -> str:
    s = re.split(r"(?<=[a-z0-9\)])[.;]\s|, (?:which|confirming|matching|supporting|aligning|as reported)", body)[0]
    s = re.sub(r",? (?:confirming|matching|supporting|aligning).*$", "", s)
    return s if len(s) <= 110 else s[:107].rsplit(" ", 1)[0] + "…"


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
