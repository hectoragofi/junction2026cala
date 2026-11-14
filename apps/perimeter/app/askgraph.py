"""The graph behind an Ask answer: every entity and link the tools read from Cala while answering.

The model only gets trimmed tool results and shows a handful of widgets. This keeps the rest, so the page can
draw it and point at what the answer left out (entities that connect two things the user asked about).

Structured reads (profile, deals, rivals, overlap) become entities and typed links. A free-text research
question becomes a node of its own: the answer and its sourced claims hang on it, and every entity Cala linked
in that answer is tied to it by the claim that names it.
"""
from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from typing import Any

from . import kg

_RANK = {"topic": -1, "company": 0, "investor": 1, "rival": 2}  # a person or a research question never changes kind
_PARENT_RELS = ("IS_DIRECT_PARENT_OF", "IS_ULTIMATE_PARENT_OF")
_ROLE_RELS = [r for r in kg._ROLE_RELS if r != "INVESTED_IN"]
# Linked in almost every answer and never the point of one: drawing them would tie unrelated research together.
_PLACES = {"GPE", "Country", "CountryRegion", "CountrySubdivision", "Municipality", "Location", "Language"}


def _source(sources: list[dict] | None) -> dict | None:
    s = next((s for s in sources or [] if s.get("url")), None)
    return {"name": s.get("name") or "Source", "url": s["url"]} if s else None


def _norm(s: str | None) -> str:
    return " ".join(kg.strip_accents(s or "").lower().split())


def _plain(s: Any) -> str:
    """One line of Cala text without markdown marks or HTML entities."""
    s = html.unescape(str(s or ""))
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return " ".join(re.sub(r"\*\*|__|`", "", s).split())


def _sentences(md: str) -> list[str]:
    """Sentences of a markdown answer, without headings: the text a name can be found in."""
    out = []
    for line in (md or "").splitlines():
        if re.match(r"\s*#", line) or re.fullmatch(r"[\s|:-]*", line):
            continue
        line = re.sub(r"\s*\|\s*", " · ", line.strip().strip("|"))
        line = _plain(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line))
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", line) if len(s.strip()) >= 12]
    return out


def _names(e: dict, type_: str) -> list[str]:
    """The ways an answer may write this entity, normalised for matching."""
    raw = [e.get("name") or ""] + [m for m in e.get("mentions") or [] if isinstance(m, str) and m != m.lower()]
    out: list[str] = []
    for r in raw:
        c = kg.clean_name(r)
        for v in ((r, c) if type_ == "Person" else (r, c, kg.short_company(c))):
            v = _norm(v)
            if len(v) >= 3 and v not in out:
                out.append(v)
    if type_ == "Person" and out and len(out[0].split()) > 1 and len(out[0].split()[-1]) >= 5:
        out.append(out[0].split()[-1])  # "Storonsky" on a second mention
    return out


def _named(text: str, names: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", text) for n in names)


def _type_label(t: str | None) -> str | None:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t).capitalize() if t and t != "Entity" else None


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.alias: dict[str, str] = {}   # every Cala id seen -> the node it was merged into
        self.by_key: dict[str, str] = {}  # normalised name -> node id (Cala keeps several records per organization)
        self.claims: dict[str, list[tuple[str, str, list[dict]]]] = {}  # research node -> (claim, normalised, sources)
        self.dirty = False

    # ---- building blocks -----------------------------------------------------------------------
    def node(self, id: str | None, name: str | None, type_: str = "Company", *, kind: str | None = None,
             sub: str | None = None, focus: bool = False) -> str | None:
        if not id or not (name or "").strip():
            return None
        person = type_ == "Person"
        label = kg.clean_name(name) if person else kg.short_company(kg.clean_name(name))
        key = ("p:" + kg.person_key(label)) if person else ("o:" + (kg.norm_key(label) or id))
        nid = self.alias.get(id) or self.by_key.get(key)
        kind = "person" if person else (kind or "company")
        if nid is None:
            nid = id
            self.nodes[nid] = {"id": nid, "name": label, "kind": kind}
            self.by_key[key] = nid
            self.dirty = True
        self.alias[id] = nid
        self.by_key.setdefault(key, nid)
        n = self.nodes[nid]
        if n["kind"] in _RANK and kind in _RANK and _RANK[kind] > _RANK[n["kind"]]:
            if n["kind"] == "topic":  # research had it as a loose mention; now it is a known organization
                n.pop("sub", None)
            n["kind"] = kind
            self.dirty = True
        if sub and not n.get("sub"):
            n["sub"] = kg.trim_text(sub, 90)
            self.dirty = True
        if focus and not n.get("focus"):
            n["focus"] = True
            self.dirty = True
        return nid

    def topic(self, id: str | None, name: str | None, type_: str | None = None) -> str | None:
        """Something Cala linked that is neither an organization nor a person: a product, a law, an industry."""
        label = kg.clean_name(name or "").strip()
        if not id or not label:
            return None
        key = "t:" + label.lower()
        nid = self.alias.get(id) or self.by_key.get(key)
        if nid is None:
            nid = id
            self.nodes[nid] = {"id": nid, "name": label, "kind": "topic"}
            if _type_label(type_):
                self.nodes[nid]["sub"] = _type_label(type_)
            self.by_key[key] = nid
            self.dirty = True
        self.alias[id] = nid
        return nid

    def edge(self, s: str | None, t: str | None, rel: str, *, label: str | None = None, date: str | None = None,
             sources: list[dict] | None = None, width: int = 80) -> None:
        if not s or not t or s == t:
            return
        key = (s, t, rel)
        if rel == "rival" and (t, s, rel) in self.edges:
            key = (t, s, rel)
        e = self.edges.get(key)
        if e is None:
            e = self.edges[key] = {"s": key[0], "t": key[1], "rel": rel}
            self.dirty = True
        for k, v in (("label", kg.trim_text(label, width) if label else None), ("date", (date or "")[:10] or None),
                     ("src", _source(sources))):
            if v and (not e.get(k) or (k == "date" and v > e[k])):
                e[k] = v
                self.dirty = True

    # ---- what each kind of read contributes ------------------------------------------------------
    def entity(self, ent: dict, *, focus: bool = False, cap: int = 80) -> str | None:
        """One retrieved entity with its neighbours: investors, portfolio, people, parents."""
        person = ent.get("type") == "Person"
        sub = None
        if not person:
            b = kg.company_basics(ent)
            sub = " · ".join(x for x in (b.get("industry"), b.get("hq")) if x) or None
        me = self.node(ent.get("id"), ent.get("name"), ent.get("type") or "Company", sub=sub, focus=focus)
        if not me:
            return None
        out, inc = ent.get("out", {}), ent.get("inc", {})
        for e in inc.get("INVESTED_IN", [])[:cap]:
            self.edge(self.node(e["id"], e["name"], e["type"], kind="investor"), me, "invested",
                      date=e.get("date"), sources=e.get("sources"))
        for e in out.get("INVESTED_IN", [])[:cap]:
            if not person:
                self.node(ent["id"], ent["name"], ent["type"], kind="investor")
            self.edge(me, self.node(e["id"], e["name"], e["type"]), "invested",
                      date=e.get("date"), sources=e.get("sources"))
        if person:
            for rel in _ROLE_RELS:
                for e in out.get(rel, [])[:cap]:
                    role = e.get("role") if rel in ("WORKS_AT", "IS_MEMBER_OF") and e.get("role") else \
                        kg.ROLE_BY_REL.get(rel)
                    self.edge(me, self.node(e["id"], e["name"], e["type"]), "role", label=role,
                              sources=e.get("sources"))
        else:
            for p in kg.people_of(ent)[: max(8, cap // 3)]:
                self.edge(self.node(p["id"], p["name"], "Person", sub=p.get("role")), me, "role",
                          label=p.get("role"), sources=p.get("sources"))
        for rel in _PARENT_RELS:
            for e in out.get(rel, [])[:cap]:
                self.edge(me, self.node(e["id"], e["name"], e["type"]), "parent", sources=e.get("sources"))
            for e in inc.get(rel, [])[:cap]:
                self.edge(self.node(e["id"], e["name"], e["type"]), me, "parent", sources=e.get("sources"))
        return me

    def deal(self, ev: dict) -> None:
        """A funding round or acquisition: its participants become links to the company it is about."""
        by_role: dict[str, list[dict]] = {}
        for p in ev.get("participants") or []:
            by_role.setdefault((p.get("role") or "").upper(), []).append(p)
        if ev.get("kind") == "mna":
            for a in by_role.get("ACQUIRER", []):
                for t in by_role.get("TARGET", []):
                    self.edge(self.node(a["id"], a["name"], a["type"]), self.node(t["id"], t["name"], t["type"]),
                              "acquired", label=ev.get("amount"), date=ev.get("date"), sources=ev.get("sources"))
            return
        rnd = ev.get("round") or kg._round_from_desc(ev.get("description") or "")
        label = " · ".join(x for x in (rnd, ev.get("amount")) if x) or None
        for issuer in by_role.get("ISSUER", [])[:1]:
            target = self.node(issuer["id"], issuer["name"], issuer["type"])
            for inv in by_role.get("INVESTOR", []):
                self.edge(self.node(inv["id"], inv["name"], inv["type"], kind="investor"), target, "invested",
                          label=label, date=ev.get("date"), sources=ev.get("sources"))

    def rivals(self, company_id: str, rivals: list[dict]) -> None:
        me = self.alias.get(company_id)
        for r in rivals:
            self.edge(me, self.node(r["id"], r["name"], kind="rival"), "rival", label=r.get("sub"))

    def shared_portfolio(self, holders: list[tuple[dict, dict | None]], cap: int = 25) -> None:
        """Companies held by two or more of these investors: the co-investments nobody asked about."""
        seen: Counter[str] = Counter()
        rows: list[tuple[str, str, dict]] = []
        for inv, ent in holders:
            a = self.alias.get(inv["id"])
            mine = set()
            for p in ((ent or {}).get("out", {}).get("INVESTED_IN") or []):
                k = self.alias.get(p["id"]) or kg.norm_key(kg.short_company(kg.clean_name(p["name"]))) or p["id"]
                if a and k not in mine:
                    mine.add(k)
                    rows.append((a, k, p))
            seen.update(mine)
        known = set(self.nodes)
        keep = {k for k, _ in seen.most_common() if seen[k] >= 2 and k not in known}
        keep = set(sorted(keep, key=lambda k: -seen[k])[:cap])
        for a, k, p in rows:
            if k in keep or k in known:
                self.edge(a, self.node(p["id"], p["name"], p["type"]), "invested",
                          date=p.get("date"), sources=p.get("sources"))

    def research(self, question: str, res: dict | None, cap: int = 30) -> str | None:
        """A free-text question to Cala's knowledge search, and what came back.

        The question is a node. Cala returns a written answer, the claims behind it (each with its source
        documents) and the entities it recognised in it: answer, claims and sources hang on the question, and
        each entity is linked to it with the claim that names it, so research joins the rest of the graph
        wherever it talks about something the other tools also read.
        """
        q = " ".join((question or "").split())
        if not q:
            return None
        res = kg._demoji(res or {})
        content = html.unescape(str(res.get("content") or res.get("text") or "")).strip()
        ctx = {k["id"]: k for k in res.get("context") or [] if isinstance(k, dict) and k.get("id")}
        claims: list[tuple[str, str, list[dict]]] = []
        for st in res.get("explainability") or []:
            text = _plain(st.get("content")) if isinstance(st, dict) else ""
            if text:
                refs = [ctx[r] for r in st.get("references") or [] if r in ctx]
                claims.append((text, _norm(text), kg._ks_sources(refs)))
        shown = [{"text": kg.trim_text(t, 300), **({"src": _source(s)} if _source(s) else {})} for t, _, s in claims[:14]]
        claims += [(s, _norm(s), []) for s in _sentences(content)]  # names that no claim carries: the answer itself
        origins = []
        for k in ctx.values():
            for o in k.get("origins") or []:
                d, s = o.get("document") or {}, o.get("source") or {}
                origins.append({"name": d.get("name") or s.get("name") or "Source", "url": d.get("url") or s.get("url"),
                                "date": None})
        sources = [{"name": s["name"], "url": s["url"]} for s in kg.merge_sources(origins, cap=8) if s.get("url")]

        rid = "q:" + hashlib.sha1(q.lower().encode()).hexdigest()[:12]
        node = self.nodes.setdefault(rid, {"id": rid, "kind": "research"})
        node.update({"name": kg.trim_text(q, 240), "text": kg.trim_block(content, 2400), "claims": shown,
                     "sources": sources})
        if ctx:
            node["sub"] = f"{len(ctx)} source{'s' if len(ctx) != 1 else ''} read"
        self.claims[rid] = claims
        self.dirty = True

        found, seen = [], set()
        for i, e in enumerate(res.get("entities") or []):
            if not isinstance(e, dict) or not e.get("id") or e["id"] in seen or not e.get("name"):
                continue
            t = e.get("entity_type") or "Entity"
            if t in _PLACES or t in kg.EVENT_TYPES:
                continue
            seen.add(e["id"])
            names = _names(e, t)
            claim = next((c for c in claims if _named(c[1], names)), None)
            found.append((e["id"] not in self.alias, claim is None, i, e, t, claim))
        found.sort(key=lambda f: f[:3])  # what the graph already holds first, then what a claim is about
        for _, _, _, e, t, claim in found[:cap]:
            nid = self.node(e["id"], e["name"], t) if t == "Person" or t in kg.COMPANY_TYPES else \
                self.topic(e["id"], e["name"], t)
            self.edge(rid, nid, "mentions", label=claim[0] if claim else None, sources=claim[2] if claim else None,
                      width=260)
        return rid

    def _link_named(self) -> None:
        """Tie research to entities the answer names in plain text but Cala did not link.

        Runs when the graph is read, so it does not matter whether the research or the entity came first.
        Matching is on the exact display name, case-sensitive, and skips short single words ("Wise", "Alan").
        """
        for rid, claims in self.claims.items():
            if not claims:
                continue
            everything = "\n".join(c[0] for c in claims)
            for nid, n in list(self.nodes.items()):
                name = n["name"]
                if n["kind"] in ("research", "topic") or (rid, nid, "mentions") in self.edges:
                    continue
                if name not in everything or (" " not in name and (len(name) < 5 or n["kind"] == "person")):
                    continue
                pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])")
                claim = next((c for c in claims if pat.search(c[0])), None)
                if claim:
                    self.edge(rid, nid, "mentions", label=claim[0], sources=claim[2], width=260)

    # ---- output ----------------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        self._link_named()
        self.dirty = False
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}
