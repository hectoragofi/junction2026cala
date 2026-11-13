"""Ask anything: Claude reads Cala's graph through a few tools and answers by composing widgets.

The model never writes prose to the user. It calls `show` once per widget; each call is streamed to the
browser the moment it is complete, so the answer builds up on screen while the model is still working.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter
from datetime import date, timedelta
from typing import Any, AsyncIterator

import anthropic
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import kg
from .cala import cala

log = logging.getLogger("perimeter.agent")
router = APIRouter(prefix="/api/agent")

MODEL = "claude-opus-5-5"
MAX_TURNS = 8
_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


SYSTEM = """You are Perimeter, an analyst for startup founders and investors. You answer questions about \
companies, investors, funding rounds and the connections between them using Cala, a knowledge graph of \
sourced public data.

You never write prose to the user. Your whole answer is a small set of widgets rendered on screen, one \
`show` call per widget. Text you write outside tool calls is discarded.

How to work
- Start with `find` to turn a name into a Cala entity. Names are ambiguous: pick the candidate whose \
description matches what the user means (a fund, not a same-named shell company). Cala often has several records for one organization: among \
the candidates the first is usually the main one, and if a profile comes back nearly empty, try the next \
matching candidate before concluding Cala has nothing.
- `profile` is fast and gives most facts: investors, portfolio, people, deal counts. `deals` adds round, \
amount, date and co-investors for the latest deals. Call independent tools in parallel.
- `rivals` and `research` are slow (up to a minute). Use them only when the question needs competitors \
or facts the graph tools cannot give.
- Use only facts returned by the tools. If Cala does not have something, say so in the headline rather \
than filling the gap from memory.

How to answer
- First widget is always a `headline`: one sentence of at most 20 words (caveats go in a widget, not here) that answers the question directly, with the key \
names and numbers in it. Tone `bad` for a risk or conflict, `good` for a clear positive, else `neutral`.
- Then at most three more widgets that carry the evidence. Fewer is better. Pick the form that fits the \
data: `stats` for two to four key numbers, `bars` to compare amounts or counts, `timeline` for dated \
events, `list` for entities with one detail each, `table` for a comparison across several attributes, \
`path` for a chain of connections (investor, company, rival).
- Finish with one `followups` widget holding three short next questions the user would likely ask.
- Keep every label short. Amounts like $205M, dates like Jan 2026. No markdown.
- Put the `src` ids from tool results in each widget's `sources` so the user can open the evidence."""

WIDGET_TYPES = ["headline", "stats", "bars", "timeline", "list", "table", "path", "followups"]

TOOLS: list[dict[str, Any]] = [
    {"name": "find", "eager_input_streaming": True,
     "description": "Search Cala for a company, investor or organization by name. Returns up to 8 candidates, best match "
                    "first, with id and a one-line description. Fast.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "profile", "eager_input_streaming": True,
     "description": "Facts about one entity by id: description, headquarters, founding year, industries, its "
                    "investors, the companies it has invested in, key people, and counts of its dated deals per "
                    "year. Fast.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "deals", "eager_input_streaming": True,
     "description": "The latest dated deals of an entity (funding rounds it raised or took part in, "
                    "acquisitions), each with company, round, amount, date and the investors on it. Takes a few "
                    "seconds.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string"}, "limit": {"type": "integer", "description": "1 to 10, default 6"}},
         "required": ["id"]}},
    {"name": "rivals", "eager_input_streaming": True,
     "description": "The closest competitors of a company by id. Slow: up to a minute the first time.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "investor_overlap", "eager_input_streaming": True,
     "description": "For one company by id: every investor on its cap table, checked against the portfolios of "
                    "those investors, listing which of the company's closest rivals each investor also backs. Use "
                    "this for any question about investors backing competitors or conflicts of interest on a "
                    "company's cap table. Can take a minute the first time.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "research", "eager_input_streaming": True,
     "description": "Ask Cala's knowledge search a free question and get a sourced written answer. Slow: about "
                    "40 seconds. Use for facts the graph tools do not cover (news, controversies, strategy).",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
    {"name": "show", "eager_input_streaming": True,
     "description": "Render one widget to the user. Fields by type. "
                    "headline: text, tone (neutral|good|bad). "
                    "stats: items [{label, value, note?}] (2-4). "
                    "bars: title, unit?, items [{label, value (number), display? (e.g. $205M)}] (2-8). "
                    "timeline: title, events [{date, title, detail?}] (2-8, newest first). "
                    "list: title, rows [{title, subtitle?, value?, id? (Cala entity id)}] (2-8). "
                    "table: title, columns [string], rows [[string]] (up to 6 rows, 4 columns). "
                    "path: title, nodes [{label, kind (investor|company|person|rival|you)}], links [string] "
                    "(one label per arrow between consecutive nodes). "
                    "followups: questions [string] (3). "
                    "Any widget may carry sources: [src ids from tool results].",
     "input_schema": {"type": "object", "properties": {
         "type": {"type": "string", "enum": WIDGET_TYPES},
         "title": {"type": "string"}, "text": {"type": "string"},
         "tone": {"type": "string", "enum": ["neutral", "good", "bad"]},
         "unit": {"type": "string"},
         "items": {"type": "array", "items": {"type": "object"}},
         "events": {"type": "array", "items": {"type": "object"}},
         "rows": {"type": "array"},
         "columns": {"type": "array", "items": {"type": "string"}},
         "nodes": {"type": "array", "items": {"type": "object"}},
         "links": {"type": "array", "items": {"type": "string"}},
         "questions": {"type": "array", "items": {"type": "string"}},
         "sources": {"type": "array", "items": {"type": "string"}}},
         "required": ["type"]}},
]


class Sources:
    """Short ids for evidence links so tool results stay small and widgets can point back at them."""

    def __init__(self) -> None:
        self.by_id: dict[str, dict] = {}
        self.by_url: dict[str, str] = {}

    def add(self, srcs: list[dict], cap: int = 2) -> list[str]:
        ids = []
        for s in srcs or []:
            url = s.get("url")
            if not url:
                continue
            if url not in self.by_url:
                sid = f"s{len(self.by_id) + 1}"
                self.by_url[url] = sid
                self.by_id[sid] = {"name": s.get("name") or "Source", "url": url, "date": s.get("date")}
            ids.append(self.by_url[url])
            if len(ids) >= cap:
                break
        return ids

    def resolve(self, ids: Any) -> list[dict]:
        out = []
        for i in ids if isinstance(ids, list) else []:
            s = self.by_id.get(i) if isinstance(i, str) else None
            if s and s not in out:
                out.append(s)
        return out[:5]


class Run:
    def __init__(self) -> None:
        self.sources = Sources()
        self.names: dict[str, str] = {}

    # ---- tools ---------------------------------------------------------------------------------
    async def find(self, name: str) -> dict:
        res = (await cala.search(name, ["Company", "Organization"]))[:8]  # Cala's own relevance order
        for e in res:
            self.names[e["id"]] = kg.clean_name(e.get("name") or "")
        return {"candidates": [{"id": e["id"], "name": self.names[e["id"]],
                                "description": kg.trim_text(e.get("description"), 140)} for e in res]}

    def _merge(self, edges: list[dict], cap: int) -> list[dict]:
        merged: list[dict] = []
        for e in edges:
            name = kg.short_company(kg.clean_name(e["name"]))
            if any(m["id"] == e["id"] or kg.same_org(m["name"], name) for m in merged):
                continue
            self.names[e["id"]] = name
            item = {"id": e["id"], "name": name}
            src = self.sources.add(e.get("sources") or [], cap=1)
            if src:
                item["src"] = src[0]
            merged.append(item)
        return merged[:cap]

    async def profile(self, id: str) -> dict:
        ent = await kg.fetch_entity(id, limit=80)
        basics = kg.company_basics(ent)
        self.names[id] = basics["name"]
        out, inc = ent.get("out", {}), ent.get("inc", {})
        edges = [e for e in out.get("PARTICIPATES_IN_CORPORATE_EVENT", []) if e.get("date")]
        as_investor = [e for e in edges if (e.get("role") or "").upper() == "INVESTOR"]
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        years = Counter(e["date"][:4] for e in as_investor)
        people = [{"name": p["name"], "role": p.get("role")} for p in kg.people_of(ent)[:8]]
        res = {"id": id, "name": basics["name"], "description": kg.trim_text(basics["description"], 220),
               "hq": basics.get("hq"), "founded": basics.get("founded"), "website": basics.get("website"),
               "industries": basics.get("industries", [])[:4],
               "investors": self._merge([e for e in inc.get("INVESTED_IN", []) if e["type"] != "Person"], 30),
               "invested_in": self._merge(out.get("INVESTED_IN", []), 80),
               "people": people,
               "own_events": [{"date": e["date"], "role": e.get("role")} for e in sorted(
                   (e for e in edges if e not in as_investor), key=lambda e: e["date"], reverse=True)[:10]]}
        if as_investor:
            res["deals_as_investor"] = {
                "on_record": len(as_investor), "last_12_months": sum(1 for e in as_investor if e["date"] >= cutoff),
                "latest": max(e["date"] for e in as_investor), "by_year": dict(sorted(years.items())[-6:])}
        return res

    async def deals(self, id: str, limit: int = 6) -> dict:
        ent = await kg.fetch_entity(id, limit=80)
        me = kg.short_company(kg.clean_name(ent["name"]))
        edges = sorted((e for e in ent.get("out", {}).get("PARTICIPATES_IN_CORPORATE_EVENT", []) if e.get("date")),
                       key=lambda e: e["date"], reverse=True)[: max(1, min(int(limit or 6), 10))]
        events = await asyncio.gather(*[kg.fetch_event(e) for e in edges])
        rows = []
        for edge, ev in zip(edges, events):
            if not ev:
                continue
            parts = ev["participants"]
            role = lambda r: [kg.clean_name(p["name"]) for p in parts if (p.get("role") or "").upper() == r]
            issuer = (role("ISSUER") or [None])[0]
            if not issuer:
                head = (ev.get("description") or "").split(". Round:")[0].strip()
                issuer = head if head and ". " not in head else None
            row = {"date": ev.get("date") or edge["date"], "kind": ev["kind"], "my_role": edge.get("role"),
                   "company": kg.short_company(issuer) if issuer else None,
                   "round": ev.get("round") or kg._round_from_desc(ev.get("description") or ""),
                   "amount": ev.get("amount"),
                   "investors": [n for n in dict.fromkeys(role("INVESTOR")) if not kg.same_org(n, me)][:8],
                   "src": self.sources.add(ev.get("sources") or [], cap=2)}
            if ev["kind"] == "mna":
                row["acquirer"], row["target"] = (role("ACQUIRER") or [None])[0], (role("TARGET") or [None])[0]
            if not row["amount"]:
                row["note"] = kg.trim_text(ev.get("description"), 160)
            rows.append({k: v for k, v in row.items() if v not in (None, [], "")})
        return {"entity": me, "deals": rows}

    async def rivals(self, id: str) -> dict:
        ent = await kg.fetch_entity(id)
        found = await kg.find_rivals(kg.company_basics(ent))
        for r in found:
            self.names[r["id"]] = r["name"]
        return {"rivals": [{"id": r["id"], "name": r["name"], "why": r.get("sub")} for r in found]}

    async def investor_overlap(self, id: str) -> dict:
        """Walk company -> its investors -> their portfolios, and flag portfolio companies that are rivals."""
        ent = await kg.fetch_entity(id)
        basics = kg.company_basics(ent)
        rivals, events = await asyncio.gather(kg.find_rivals(basics), kg.company_events(ent))
        investors = kg.investors_of(ent, events)[:15]
        held = await asyncio.gather(*[kg.safe_entity(i["id"], 80) for i in investors])
        rows = []
        for inv, inv_ent in zip(investors, held):
            portfolio = (inv_ent or {}).get("out", {}).get("INVESTED_IN", [])
            also = []
            for r in rivals:
                edge = next((p for p in portfolio if p["id"] == r["id"] or kg.same_org(
                    kg.short_company(kg.clean_name(p["name"])), r["name"])), None)
                if edge:
                    also.append({"rival": r["name"], "src": self.sources.add(edge.get("sources") or [], cap=1)})
            self.names[inv["id"]] = inv["name"]
            rows.append({"id": inv["id"], "investor": inv["name"], "since": (inv.get("first_date") or "")[:4] or None,
                         "portfolio_size": len(portfolio), "also_backs_rivals": also})
        rows.sort(key=lambda r: -len(r["also_backs_rivals"]))
        return {"company": basics["name"], "rivals_checked": [r["name"] for r in rivals], "investors": rows}

    async def research(self, question: str) -> dict:
        res = await cala.ksearch(question)
        return {"answer": kg.trim_text(res.get("content") or "", 3500),
                "src": self.sources.add(kg._ks_sources(res.get("context") or []), cap=4)}

    def step(self, name: str, args: dict) -> str | None:
        who = self.names.get(args.get("id", ""), "")
        return {"find": f"Searching Cala for {args.get('name', '')}",
                "profile": f"Reading {who}" if who else "Reading the graph",
                "deals": f"Pulling {who}'s deals" if who else "Pulling deals",
                "rivals": f"Finding {who}'s rivals" if who else "Finding rivals",
                "investor_overlap": f"Checking {who}'s investors against its rivals" if who else "Checking investors",
                "research": "Asking Cala's knowledge search"}.get(name)

    # ---- widgets -------------------------------------------------------------------------------
    def widget(self, w: Any) -> dict | None:
        """Validate a `show` input (eager streaming skips server-side validation) and resolve its sources."""
        if not isinstance(w, dict) or w.get("type") not in WIDGET_TYPES:
            return None
        need = {"headline": ("text", str), "stats": ("items", list), "bars": ("items", list),
                "timeline": ("events", list), "list": ("rows", list), "table": ("rows", list),
                "path": ("nodes", list), "followups": ("questions", list)}[w["type"]]
        if not isinstance(w.get(need[0]), need[1]) or not w[need[0]]:
            return None
        if w["type"] == "bars":
            w["items"] = [i for i in w["items"] if isinstance(i, dict) and isinstance(i.get("value"), (int, float))]
            if not w["items"]:
                return None
        if w["type"] == "table" and not all(isinstance(r, list) for r in w["rows"]):
            return None
        if w["type"] in ("stats", "timeline", "list", "path"):
            key = need[0]
            w[key] = [i for i in w[key] if isinstance(i, dict)]
            if not w[key]:
                return None
        w["sources"] = self.sources.resolve(w.get("sources"))
        return w


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class Turn(BaseModel):
    q: str
    headline: str | None = None


class AskIn(BaseModel):
    q: str
    history: list[Turn] = []
    profile: dict | None = None  # who is asking: {role, my_company, portfolio, rivals}


async def answer(body: AskIn) -> AsyncIterator[str]:
    run = Run()
    context = "".join(f"Earlier question: {t.q}\nYour headline then: {t.headline or '(none)'}\n\n"
                      for t in body.history[-4:])
    if body.profile:
        who = json.dumps({k: v for k, v in body.profile.items() if v}, ensure_ascii=False)[:1500]
        context = ("About the person asking (use it to resolve 'my company', 'my portfolio', 'my rivals'): "
                   f"{who}\n\n{context}")
    messages: list[dict] = [{"role": "user", "content": f"{context}Question: {body.q.strip()}"}]
    shown = 0
    try:
        for _ in range(MAX_TURNS):
            async with client().beta.messages.stream(
                model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            ) as stream:
                async for event in stream:
                    if event.type != "content_block_stop" or event.content_block.type != "tool_use":
                        continue
                    block = event.content_block
                    if block.name == "show":
                        w = run.widget(block.input)
                        if w:
                            shown += 1
                            yield sse("widget", w)
                    else:
                        text = run.step(block.name, block.input if isinstance(block.input, dict) else {})
                        if text:
                            yield sse("step", {"text": text})
                response = await stream.get_final_message()

            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason in ("refusal", "max_tokens") or not uses:
                break
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue

            async def execute(b) -> dict:
                args = b.input if isinstance(b.input, dict) else {}
                if b.name == "show":
                    ok = isinstance(args, dict) and args.get("type") in WIDGET_TYPES
                    return {"type": "tool_result", "tool_use_id": b.id, "is_error": not ok,
                            "content": "shown" if ok else "Invalid widget: check the fields for this type."}
                try:
                    fn = getattr(run, b.name)
                    wanted = {k: v for k, v in args.items() if k in ("name", "id", "limit", "question")}
                    result = await asyncio.wait_for(fn(**wanted), timeout=150)
                    return {"type": "tool_result", "tool_use_id": b.id,
                            "content": json.dumps(result, ensure_ascii=False)}
                except Exception as e:  # tool failures go back to the model, which can route around them
                    log.warning("tool %s failed: %s", b.name, e)
                    return {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                            "content": f"{type(e).__name__}: {str(e)[:200]}"}

            results = await asyncio.gather(*[execute(b) for b in uses])
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": list(results)})
        if not shown:
            yield sse("widget", {"type": "headline", "tone": "neutral", "sources": [],
                                 "text": "I could not put an answer together for that. Try naming the company "
                                         "or investor."})
        yield sse("done", {})
    except anthropic.RateLimitError:
        yield sse("error", {"message": "The model is rate limited right now. Try again in a moment."})
    except anthropic.APIConnectionError:
        yield sse("error", {"message": "Lost the connection to the model. Try again."})
    except anthropic.APIStatusError as e:
        log.error("anthropic %s: %s", e.status_code, e.message)
        yield sse("error", {"message": f"The model returned an error ({e.status_code})."})
    except Exception as e:
        log.exception("agent failed")
        yield sse("error", {"message": f"Something went wrong: {type(e).__name__}."})


@router.post("")
async def ask(body: AskIn):
    if not body.q.strip():
        return StreamingResponse(iter([sse("error", {"message": "Ask a question."})]), media_type="text/event-stream")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return StreamingResponse(iter([sse("error", {"message": "ANTHROPIC_API_KEY is not set on the server."})]),
                                 media_type="text/event-stream")
    return StreamingResponse(answer(body), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
