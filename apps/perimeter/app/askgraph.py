"""The graph behind an Ask answer: every entity and link the tools read from Cala while answering.

The model only gets trimmed tool results and shows a handful of widgets. This keeps the rest, so the page can
draw it and point at what the answer left out (entities that connect two things the user asked about).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from . import kg

_RANK = {"company": 0, "investor": 1, "rival": 2, "person": 3}
_PARENT_RELS = ("IS_DIRECT_PARENT_OF", "IS_ULTIMATE_PARENT_OF")
_ROLE_RELS = [r for r in kg._ROLE_RELS if r != "INVESTED_IN"]


def _source(sources: list[dict] | None) -> dict | None:
    s = next((s for s in sources or [] if s.get("url")), None)
    return {"name": s.get("name") or "Source", "url": s["url"]} if s else None


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.alias: dict[str, str] = {}   # every Cala id seen -> the node it was merged into
        self.by_key: dict[str, str] = {}  # normalised name -> node id (Cala keeps several records per organization)
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
        n = self.nodes[nid]
        if n["kind"] != "person" and kind != "person" and _RANK[kind] > _RANK[n["kind"]]:
            n["kind"] = kind
            self.dirty = True
        if sub and not n.get("sub"):
            n["sub"] = kg.trim_text(sub, 90)
            self.dirty = True
        if focus and not n.get("focus"):
            n["focus"] = True
            self.dirty = True
        return nid

    def edge(self, s: str | None, t: str | None, rel: str, *, label: str | None = None, date: str | None = None,
             sources: list[dict] | None = None) -> None:
        if not s or not t or s == t:
            return
        key = (s, t, rel)
        if rel == "rival" and (t, s, rel) in self.edges:
            key = (t, s, rel)
        e = self.edges.get(key)
        if e is None:
            e = self.edges[key] = {"s": key[0], "t": key[1], "rel": rel}
            self.dirty = True
        for k, v in (("label", kg.trim_text(label, 80) if label else None), ("date", (date or "")[:10] or None),
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

    # ---- output ----------------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        self.dirty = False
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}
