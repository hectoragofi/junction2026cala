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
PROFILES_DIR = CACHE_DIR / "profiles"

# Real companies Cala knows well, chosen for overlapping investors, M&A and recent rounds.
DEMO_PORTFOLIO = [
    "327d0698-9bb0-4250-a2fd-a5d9cb5a6810",  # Mollie (Amsterdam payments)
    "151397f7-1f81-45a7-9cce-9ba4956d52a5",  # Qonto (Paris business banking)
    "416166a8-95e7-4cd6-baad-3208cb8d4299",  # Pennylane (Paris accounting)
    "11267552-e210-40ec-aafd-526c205f6225",  # Pigment (Paris planning software)
]
DEMO_PID = "demo"
PID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
BUILD_SLOTS = max(1, int(os.environ.get("BUILD_SLOTS", "2") or 2))
_BUILD_SEM: asyncio.Semaphore | None = None
QUEUE: list[str] = []  # pids waiting for a build slot, in order


def _sem() -> asyncio.Semaphore:
    global _BUILD_SEM
    if _BUILD_SEM is None:
        _BUILD_SEM = asyncio.Semaphore(BUILD_SLOTS)
    return _BUILD_SEM


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class Space:
    """One perimeter: the shared demo (pid "demo", state.json) or a visitor's own profile."""

    def __init__(self, pid: str):
        self.pid = pid
        self.state: dict = {"portfolio": [], "portfolio_ids": [], "built": None, "built_at": None}
        self.build: dict = {"task": None, "progress": None, "error": None, "partial": None}
        self.profile: dict | None = None  # None for the demo

    @property
    def demo(self) -> bool:
        return self.pid == DEMO_PID

    @property
    def state_file(self) -> Path:
        return STATE_FILE if self.demo else PROFILES_DIR / f"{self.pid}.state.json"

    @property
    def profile_file(self) -> Path:
        return PROFILES_DIR / f"{self.pid}.json"

    @property
    def role(self) -> str:
        return (self.profile or {}).get("role") or "investor"

    def load(self):
        if not self.demo and self.profile_file.exists():
            self.profile = json.loads(self.profile_file.read_text(encoding="utf-8"))
            self.state["portfolio_ids"] = self.profile.get("portfolio_ids") or []
            self.state["portfolio"] = self.profile.get("portfolio") or []
        if self.state_file.exists():
            try:
                st = json.loads(self.state_file.read_text(encoding="utf-8"))
                if self.demo:
                    self.state.update(st)
                else:
                    self.state.update(built=st.get("built"), built_at=st.get("built_at"))
            except Exception as e:
                log.warning("state load failed (%s): %s", self.pid, e)

    def save_state(self):
        if self.demo:
            _write_json(self.state_file, self.state)
        else:
            _write_json(self.state_file, {"built": self.state.get("built"), "built_at": self.state.get("built_at")})

    def save_profile(self):
        if self.demo or self.profile is None:
            return
        self.profile.update(portfolio_ids=self.state.get("portfolio_ids") or [],
                            portfolio=self.state.get("portfolio") or [], updated_at=_now())
        _write_json(self.profile_file, self.profile)

    def building(self) -> bool:
        t = self.build.get("task")
        return bool(t and not t.done())

    def partial(self) -> dict | None:
        """While a new portfolio's first build runs (no finished build yet), what has landed so far."""
        if self.state.get("built") or not self.building():
            return None
        return self.build.get("partial")

    def queued(self) -> int | None:
        return QUEUE.index(self.pid) + 1 if self.pid in QUEUE else None

    def start_build(self):
        self.cancel_build()
        self.build["task"] = asyncio.create_task(_build(self, list(self.state.get("portfolio_ids") or [])))

    def cancel_build(self):
        t = self.build.get("task")
        if t and not t.done():
            t.cancel()


SPACES: dict[str, Space] = {}


def demo_space() -> Space:
    s = SPACES.get(DEMO_PID)
    if not s:
        s = SPACES[DEMO_PID] = Space(DEMO_PID)
        s.load()
    return s


def get_space(pid: str | None) -> Space | None:
    """A visitor's own profile space, loaded from disk on first use (None when it doesn't exist)."""
    if not pid or pid == DEMO_PID or not PID_RE.match(pid):
        return None
    s = SPACES.get(pid)
    if s:
        return s
    s = Space(pid)
    if not s.profile_file.exists():
        return None
    try:
        s.load()
    except Exception as e:
        log.warning("profile load failed (%s): %s", pid, e)
        return None
    SPACES[pid] = s
    if s.state.get("portfolio_ids") and not s.state.get("built"):
        s.start_build()  # resume a build interrupted by a restart
    return s


def _identity(request: Request) -> str | None:
    """The visitor's own profile id: X-Profile header, ?pid= (EventSource), or the pid cookie."""
    pid = (request.headers.get("x-profile") or request.query_params.get("pid") or request.cookies.get("pid") or "").strip()
    return pid if pid == DEMO_PID or PID_RE.match(pid) else None


def _viewing_demo(request: Request) -> bool:
    return (request.headers.get("x-view") or request.query_params.get("view") or "") == "demo"


def active(request: Request) -> Space:
    """The space a data request reads: the visitor's own profile, or the shared demo (no profile / "Explore")."""
    if _viewing_demo(request):
        return demo_space()
    return get_space(_identity(request)) or demo_space()


async def _company_card(eid: str) -> dict | None:
    ent = await kg.safe_entity(eid)
    if not ent:
        return None
    c = kg.company_basics(ent)
    return {k: c.get(k) for k in ("id", "name", "description", "website", "hq", "founded")}


async def _build(space: Space, ids: list[str]):
    b = space.build
    b.update(error=None, partial=None, progress=None)

    def progress(msg, partial=None):
        b["progress"] = msg
        if partial is not None:
            b["partial"] = partial
    QUEUE.append(space.pid)
    try:
        async with _sem():  # cold builds hit Cala hard (~20 calls/min): only BUILD_SLOTS at a time
            QUEUE.remove(space.pid)
            res = await build(ids, progress=progress)
            space.state["built"] = res
            space.state["built_at"] = res["built_at"]
            if res.get("portfolio"):
                space.state["portfolio"] = res["portfolio"]
            space.save_state()
            if space.profile is not None:
                if space.role == "founder":
                    cos = (res.get("perimeter") or {}).get("companies") or []
                    space.profile["watch_rivals"] = [{"id": r["id"], "name": r["name"]}
                                                     for r in ((cos[0].get("rivals") if cos else None) or [])]
                space.save_profile()
            log.info("perimeter %s built in %ss", space.pid, res.get("build_seconds"))
    except asyncio.CancelledError:
        raise
    except Exception as e:  # keep the previous build
        log.exception("build failed (%s)", space.pid)
        b["error"] = str(e)
    finally:
        if space.pid in QUEUE:
            QUEUE.remove(space.pid)
        b["progress"] = None
        b["partial"] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    d = demo_space()
    if d.state.get("portfolio_ids") and not d.state.get("built"):
        d.start_build()
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
async def get_portfolio(request: Request):
    s = active(request)
    part = s.partial()
    return {"companies": s.state.get("portfolio") or [], "building": s.building(), "built_at": s.state.get("built_at"),
            "progress": s.build.get("progress"), "error": s.build.get("error"),
            **({"queued": s.queued()} if s.queued() else {}),
            **({"status": part["status"]} if part else {})}


class PortfolioIn(BaseModel):
    ids: list[str]


DEMO_LOCK = os.environ.get("DEMO_LOCK", "") == "1"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def _locked(request: Request) -> bool:
    """With DEMO_LOCK=1 public visitors cannot replace or rebuild the shared demo portfolio."""
    return DEMO_LOCK and not (ADMIN_TOKEN and request.headers.get("x-admin-token") == ADMIN_TOKEN)


def _clean_ids(ids: list[str] | None) -> list[str]:
    return list(dict.fromkeys(i.strip() for i in ids or [] if i and i.strip()))[:12]


async def _set_ids(s: Space, ids: list[str]):
    """Replace a space's companies and start a fresh build (no-op when unchanged and already built)."""
    if ids == (s.state.get("portfolio_ids") or []) and (s.state.get("built") or s.building()):
        return
    if not ids:
        s.cancel_build()
        s.state.update({"portfolio_ids": [], "portfolio": [], "built": None, "built_at": None})
        s.save_state()
        return
    cards = [c for c in await asyncio.gather(*[_company_card(i) for i in ids]) if c]
    if not cards:
        raise HTTPException(404, "Cala has none of those companies")
    s.state.update({"portfolio_ids": [c["id"] for c in cards], "portfolio": cards, "built": None, "built_at": None})
    s.save_state()
    s.start_build()


@app.post("/api/portfolio")
async def set_portfolio(body: PortfolioIn, request: Request):
    ids = _clean_ids(body.ids)
    if not ids:
        raise HTTPException(400, "ids required")
    s = active(request)
    if s.demo:
        if ids != DEMO_PORTFOLIO and _locked(request):
            raise HTTPException(403, "The shared demo is locked. Make your own profile to watch your companies.")
    elif s.role == "founder":
        ids = ids[:1]
    await _set_ids(s, ids)
    if s.profile is not None:
        if s.role == "founder":
            s.profile["my_company"] = (s.state.get("portfolio") or [None])[0]
        s.save_profile()
    return {"ok": True}


@app.post("/api/portfolio/demo")
async def demo_portfolio(request: Request):
    d = demo_space()
    if d.state.get("portfolio_ids") == DEMO_PORTFOLIO and (d.state.get("built") or d.building()):
        return {"ok": True}
    await _set_ids(d, DEMO_PORTFOLIO)
    return {"ok": True}


@app.post("/api/rebuild")
async def rebuild(request: Request):
    s = active(request)
    if s.demo and _locked(request) and s.state.get("built"):
        raise HTTPException(403, "Rebuild is disabled on the shared demo.")
    if not s.state.get("portfolio_ids"):
        raise HTTPException(400, "no portfolio")
    s.start_build()
    return {"ok": True}


# --------------------------------------------------------------------------- profiles
def _context(s: Space) -> dict:
    """Compact, cheap summary of what this profile watches (read by other agents/workstreams)."""
    port = [{"id": c["id"], "name": c["name"]} for c in s.state.get("portfolio") or []]
    rivals = []
    b = s.state.get("built")
    if b:
        seen = set()
        for c in (b.get("perimeter") or {}).get("companies") or []:
            for r in c.get("rivals") or []:
                if r.get("id") not in seen:
                    seen.add(r.get("id"))
                    rivals.append({"id": r["id"], "name": r["name"]})
    role = "investor" if s.demo else s.role
    mc = (s.profile or {}).get("my_company") if role == "founder" else None
    return {"role": role, "demo": s.demo,
            "my_company": {"id": mc["id"], "name": mc["name"]} if mc else None,
            "portfolio": port, "rivals": rivals[:24], "built_at": s.state.get("built_at")}


def _profile_out(p: dict | None) -> dict | None:
    if p is None:
        return None
    return {k: p.get(k) for k in ("role", "name", "fund_or_company_name", "my_company", "portfolio_ids", "portfolio",
                                  "watch_rivals", "created_at", "updated_at")}


@app.get("/api/profile")
async def get_profile(request: Request):
    pid = _identity(request)
    own = get_space(pid)
    view = active(request)
    return {"pid": pid, "exists": own is not None, "viewing": "demo" if view.demo else "me",
            "demo_locked": _locked(request), "profile": _profile_out(own.profile) if own else None,
            "context": _context(view)}


class ProfileIn(BaseModel):
    role: str | None = None                  # "founder" | "investor"
    name: str | None = None
    fund_or_company_name: str | None = None
    my_company_id: str | None = None         # founder: their own company
    portfolio_ids: list[str] | None = None   # investor: the companies they watch
    watch_rivals: list[dict] | None = None


@app.put("/api/profile")
async def put_profile(body: ProfileIn, request: Request):
    pid = _identity(request)
    if not pid:
        raise HTTPException(400, "Send your profile id in the X-Profile header (or the pid cookie).")
    if body.role is not None and body.role not in ("founder", "investor"):
        raise HTTPException(400, "role must be founder or investor")
    if pid == DEMO_PID:  # the shared demo has no profile, only its portfolio
        if _locked(request):
            raise HTTPException(403, "The shared demo is locked. Make your own profile to change companies.")
        if body.portfolio_ids is not None:
            await _set_ids(demo_space(), _clean_ids(body.portfolio_ids))
        return await get_profile(request)
    s = get_space(pid)
    if s is None:
        s = Space(pid)
        s.profile = {"role": body.role or "investor", "created_at": _now(), "watch_rivals": []}
        SPACES[pid] = s
    p = s.profile
    old_role = p.get("role")
    for k in ("role", "name", "fund_or_company_name"):
        v = getattr(body, k)
        if v is not None:
            p[k] = v.strip()[:80] if isinstance(v, str) else v
    if body.watch_rivals is not None:
        p["watch_rivals"] = body.watch_rivals[:24]
    cur = s.state.get("portfolio_ids") or []
    ids = None
    if p["role"] == "founder":
        if body.my_company_id:
            ids = [body.my_company_id.strip()]
        elif body.portfolio_ids is not None:
            ids = _clean_ids(body.portfolio_ids)[:1]
        elif old_role != "founder" and len(cur) > 1:
            ids = cur[:1]  # switching seat: keep the first company as "mine"
    elif body.portfolio_ids is not None:
        ids = _clean_ids(body.portfolio_ids)
    if ids is not None:
        await _set_ids(s, ids)
    if p["role"] == "founder":
        p["my_company"] = (s.state.get("portfolio") or [None])[0]
    else:
        p.pop("my_company", None)
    s.save_profile()
    return await get_profile(request)


@app.post("/api/profile/reset")
async def reset_profile(request: Request):
    pid = _identity(request)
    if not pid or pid == DEMO_PID:
        raise HTTPException(400, "Nothing to reset")
    s = get_space(pid)
    if s:
        s.cancel_build()
        SPACES.pop(pid, None)
        for f in (s.profile_file, s.state_file):
            f.unlink(missing_ok=True)
    return {"ok": True}


def _empty_perimeter():
    return {"companies": [], "stats": {"rivals": 0, "investors": 0, "people": 0, "countries": 0, "entities": 0,
                                       "facts": 0}, "signals": []}


@app.get("/api/perimeter")
async def perimeter(request: Request):
    s = active(request)
    b = s.state.get("built")
    if not b:
        part = s.partial()
        if part:
            return {**part["perimeter"], "building": True, "status": part["status"], "partial": True}
        return {**_empty_perimeter(), "building": s.building()}
    return {**b["perimeter"], "building": s.building(), "built_at": s.state.get("built_at")}


@app.get("/api/feed")
async def feed(request: Request):
    s = active(request)
    b = s.state.get("built")
    part = s.partial()
    if not b and part:
        return {**part["feed"], "building": True, "status": part["status"], "partial": True}
    if not b:
        return {"summary": "Mapping your perimeter…" if s.building() else "Add companies to start watching.",
                "items": [], "building": s.building()}
    return {**b["feed"], "building": s.building(), "built_at": s.state.get("built_at")}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/check/stream")
async def check_stream(q: str, request: Request):
    s = active(request)
    pids = set(s.state.get("portfolio_ids") or [])
    pnames = [c["name"] for c in s.state.get("portfolio") or []]

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
        ents.append({"id": e.get("id"), "name": kg.clean_name(e.get("name") or ""),
                     "type": "Company" if t in kg.COMPANY_TYPES else t})
    return {"answer_md": res.get("content") or "", "sources": sources, "entities": ents[:20]}


@app.post("/api/ask")
async def ask(body: AskIn, request: Request):
    s = active(request)
    q = (body.q or "").strip()
    if not q:
        raise HTTPException(400, "q required")
    t0 = time.monotonic()
    local = _local_answer(q, s)
    if local:
        return {**local, "seconds": round(time.monotonic() - t0, 1)}
    try:
        res = await cala.ksearch(_with_portfolio(q, s))
    except Exception as e:
        raise HTTPException(502, f"Cala: {e}")
    return {**ask_payload(res), "seconds": round(time.monotonic() - t0, 1)}


_MY = re.compile(r"\b(my|our) (portfolio( companies)?|companies|company|startup|bets|investments)\b", re.I)


def _with_portfolio(q: str, s: Space) -> str:
    """Cala doesn't know the user's portfolio: name it when the question refers to it."""
    names = [c["name"] for c in s.state.get("portfolio") or []]
    if not names or not (_MY.search(q) or re.search(r"\b(rivals?|competitors?)\b", q, re.I)):
        return q
    q2 = _MY.sub(", ".join(names), q)
    rivals = (s.state.get("built") or {}).get("rivals_index") or {}
    label = "My company" if (not s.demo and s.role == "founder") else "Portfolio companies"
    ctx = f" ({label}: {', '.join(names)}"
    if rivals:
        ctx += "; their closest rivals: " + ", ".join(v["name"] for v in list(rivals.values())[:16])
    return q2 + ctx + ")"


def _local_answer(q: str, s: Space) -> dict | None:
    """Overlap questions are answered from the built perimeter (Cala facts, already sourced), instantly."""
    b = s.state.get("built")
    if not b:
        return None
    ql = q.lower()
    items = (b.get("feed") or {}).get("items") or []
    if re.search(r"\binvest|back", ql) and re.search(r"\brival|competitor", ql):
        rows = [i for i in items if i["kind"] == "overlap_investor"]
        head = "| Investor | Backs (yours) | Also backs | Rival of |\n|---|---|---|---|\n"
        body = "".join(f"| {i['investor']['name']} | {i['company']['name']} | {i['subject']['name']} | "
                       f"{i['subject']['relation'].replace('rival of ', '')} |\n" for i in rows)
        intro = (f"{len(rows)} investor overlap{'s' if len(rows) != 1 else ''} across your portfolio, from Cala's "
                 f"investment records:\n\n" if rows else "No investor in your portfolio also backs one of the "
                                                         "closest rivals Cala lists.")
        ents = [i["investor"] for i in rows] + [i["subject"] for i in rows]
    elif re.search(r"\bboard|more than one|sits on|people", ql) and re.search(r"\bboard|compan|perimeter", ql):
        sigs = [s for s in (b.get("perimeter") or {}).get("signals", []) if s["kind"] in ("Board seat", "Talent")]
        rows = sigs
        head = "| Person | Link |\n|---|---|\n"
        body = "".join(f"| {s['entities'][0]['name']} | {s['text']} |\n" for s in sigs)
        intro = (f"{len(sigs)} people link more than one company around your portfolio:\n\n" if sigs else
                 "Cala lists nobody who sits on more than one board around your companies. Founders, executives "
                 "and board members were checked for each portfolio company.")
        ents = [s["entities"][0] for s in sigs]
    elif re.search(r"\brivals?\b|competitors?", ql) and re.search(r"rais|fund|round", ql):
        rows = [i for i in items if i["kind"] == "funding" and i.get("subject")]
        recent = [i for i in rows if (kg.months_ago(i.get("date")) or 99) <= 12]
        lead = ""
        if re.search(r"this year|last (12 months|year)|recent", ql):
            if recent:
                rows = recent
            elif rows:
                lead = "None in the last 12 months. The most recent ones in Cala:\n\n"
        head = "| Rival | Round | Date | Rival of |\n|---|---|---|---|\n"

        def when(d):
            try:
                x = datetime.strptime(d[:10], "%Y-%m-%d")
                return f"{x.day} {x:%b %Y}"
            except (TypeError, ValueError):
                return d or "—"
        body = "".join(f"| {i['subject']['name']} | {i['title'].split(' raised ', 1)[-1]} | {when(i.get('date'))} "
                       f"| {i['company']['name']} |\n" for i in rows)
        intro = lead or (f"{len(rows)} funding round{'s' if len(rows) != 1 else ''} by your companies' closest "
                         f"rivals in Cala:\n\n" if rows else
                         "Cala has no recent funding rounds for your companies' closest rivals.")
        ents = [i["subject"] for i in rows]
        bodies = [i.get("body") or "" for i in rows if "Investors:" in (i.get("body") or "")]
        if bodies:
            body += "\nInvestors named in Cala:\n\n" + "\n".join(
                f"- **{i['subject']['name']}** ({i['title'].split(' raised ', 1)[-1]}): "
                f"{i['body'].split('Investors:', 1)[1].strip()}"
                for i in rows if "Investors:" in (i.get("body") or ""))
    else:
        return None
    srcs = kg.merge_sources(*[r.get("sources") or [] for r in rows], cap=12)
    seen, refs = set(), []
    for e in ents:
        if e.get("id") and e["id"] not in seen:
            seen.add(e["id"])
            refs.append({"id": e["id"], "name": e["name"], "type": e.get("type") or "Company"})
    return {"answer_md": intro + (head + body if rows else ""), "sources": srcs, "entities": refs[:20]}


class DraftIn(BaseModel):
    item_id: str


def _human_date(d: str) -> str:
    """'2026-08-25' -> '25 August 2026', '2026-08' -> 'August 2026', '2026' stays."""
    try:
        if len(d) >= 10:
            x = datetime.strptime(d[:10], "%Y-%m-%d")
            return f"{x.day} {x:%B %Y}"
        if len(d) == 7:
            return datetime.strptime(d, "%Y-%m").strftime("%B %Y")
    except ValueError:
        pass
    return d


def _template_note(it: dict) -> dict:
    company = it["company"]["name"]
    subj = it["title"]
    lines = [f"Hi {company} team,", ""]
    lines.append(f"Flagging something from our portfolio watch: {it['title'].rstrip('.')}.")
    if it.get("body"):
        lines += ["", it["body"].strip()]
    when = f" ({_human_date(it['date'])})" if it.get("date") else ""
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
async def draft(body: DraftIn, request: Request):
    b = active(request).state.get("built") or {}
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
# Founder-side investor diligence (owned by a separate workstream); enabled once app/investor.py exists.
try:
    from .investor import router as investor_router
except ImportError:
    investor_router = None
if investor_router is not None:
    app.include_router(investor_router)

    @app.get("/investors", include_in_schema=False)
    async def investors_page():
        return FileResponse(WEB_DIR / "investor.html", headers={"Cache-Control": "no-cache"})

# Ask anything: Claude answers with generated widgets over Cala (app/agent.py, web/ask.html).
try:
    from .agent import router as agent_router
except ImportError:
    agent_router = None
if agent_router is not None:
    app.include_router(agent_router)

    @app.get("/ask", include_in_schema=False)
    async def ask_page():
        return FileResponse(WEB_DIR / "ask.html", headers={"Cache-Control": "no-cache"})


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
