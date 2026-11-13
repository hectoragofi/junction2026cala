"""Live layer of the feed: what changed around the perimeter in the last few days.

Cala gives the perimeter (portfolio companies, their rivals) and dated facts that can be months old.
This module asks Context.dev what happened since, and turns it into feed items of the same shape:

- news about each company in the perimeter (`news` / `regulatory` / `legal` / `funding` / `mna`)
- changes detected by page monitors, e.g. a rival's pricing page (`page_change`)

Nothing enters unless it is attached to a company Cala already put in the perimeter. A match by exact
domain is trusted; a match by name carries Context.dev's confidence and may come out as `possible`.
Without CONTEXT_DEV_API_KEY the module is inert and the feed is exactly what it was before.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from . import kg
from .cala import CACHE_DIR
from .contextdev import ContextDevError, ctx
from .perimeter import _sev_rank, summarize

log = logging.getLogger("perimeter.live")

NEWS_DAYS = int(os.environ.get("LIVE_NEWS_DAYS", "7"))          # how far back a sweep looks
KEEP_DAYS = int(os.environ.get("LIVE_KEEP_DAYS", "14"))         # how long an item stays in the feed
REFRESH_MIN = float(os.environ.get("LIVE_REFRESH_MIN", "30"))   # minutes between sweeps
NEWS_LIMIT = int(os.environ.get("LIVE_NEWS_LIMIT", "10"))       # articles per company per sweep (1 credit per 10)
POSSIBLE_BELOW = float(os.environ.get("LIVE_POSSIBLE_BELOW", "0.85"))
DROP_BELOW = float(os.environ.get("LIVE_DROP_BELOW", "0.6"))
MIN_GAP_S = 60.0                                                # manual refreshes closer than this are ignored

LIVE_FILE = CACHE_DIR / "live.json"
MONITORS_FILE = CACHE_DIR / "live-monitors.json"   # monitor id -> company id, for pages off the company's domain

LIVE: dict = {"items": {}, "updated_at": None, "last_error": None, "targets": 0}
_last_sweep = 0.0
_lock = asyncio.Lock()

_FUNDING = re.compile(r"\b(raises?|raised|secures?|secured|closes?|closed|lands?|bags?)\b[^.]{0,40}(€|\$|£|\d)"
                      r"|\b(funding|financing|investment) round\b|\bseries [a-h]\b|\b(pre-)?seed round\b"
                      r"|\bvaluation of\b|\bvalued at\b", re.I)
_MNA = re.compile(r"\b(acquires?|acquired|acquisition of|to acquire|to buy|buys|bought|takeover|merger with"
                  r"|merges with|agreed to (buy|acquire))\b", re.I)


# --------------------------------------------------------------------------- store
def load():
    if LIVE_FILE.exists():
        try:
            LIVE.update(json.loads(LIVE_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("live state load failed: %s", e)


def save():
    tmp = LIVE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(LIVE, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIVE_FILE)


def monitor_map() -> dict:
    try:
        return json.loads(MONITORS_FILE.read_text(encoding="utf-8")) if MONITORS_FILE.exists() else {}
    except Exception:
        return {}


def remember_monitor(monitor_id: str, company_id: str):
    m = monitor_map()
    m[monitor_id] = company_id
    MONITORS_FILE.write_text(json.dumps(m), encoding="utf-8")


# --------------------------------------------------------------------------- watchlist
def domain_of(website: str | None) -> str | None:
    if not website:
        return None
    w = website.strip()
    host = urlparse(w if "//" in w else "//" + w).hostname or ""
    host = re.sub(r"^www\.", "", host.lower())
    return host if "." in host else None


def watchlist(built: dict | None) -> list[dict]:
    """Companies to watch: every portfolio company and its rivals, each tied to its Cala entity."""
    out: dict[str, dict] = {}
    for c in ((built or {}).get("perimeter") or {}).get("companies") or []:
        ref = {"id": c["id"], "name": c["name"], "type": "Company"}
        out[c["id"]] = {"id": c["id"], "name": c["name"], "domain": domain_of(c.get("website")),
                        "role": "portfolio", "company": ref, "subject": None}
    for c in ((built or {}).get("perimeter") or {}).get("companies") or []:
        ref = {"id": c["id"], "name": c["name"], "type": "Company"}
        for r in c.get("rivals") or []:
            if r["id"] in out:
                continue
            out[r["id"]] = {"id": r["id"], "name": r["name"], "domain": domain_of(r.get("website")),
                            "role": "rival", "company": ref,
                            "subject": {"id": r["id"], "name": r["name"], "type": "Company",
                                        "relation": f"rival of {c['name']}"}}
    return list(out.values())


# --------------------------------------------------------------------------- mapping to feed items
def _id(*parts: str) -> str:
    return "live-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _day(iso: str | None) -> str | None:
    """ISO timestamp -> UTC calendar day."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo:
            d = d.astimezone(timezone.utc)
        return d.date().isoformat()
    except ValueError:
        return str(iso)[:10] if re.match(r"\d{4}-\d{2}-\d{2}", str(iso)) else None


def _fresh(day: str | None, days: int) -> bool:
    if not day:
        return False
    try:
        return date.fromisoformat(day) >= datetime.now(timezone.utc).date() - timedelta(days=days)
    except ValueError:
        return False


def _clip(s: str | None, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def news_item(article: dict, target: dict) -> dict | None:
    """One Context.dev article about `target` -> a feed item, or None if it should not be shown."""
    title = _clip(article.get("title"), 140)
    url = article.get("url")
    day = _day(article.get("published_at"))
    if not title or not url or not _fresh(day, NEWS_DAYS):
        return None
    by_domain = bool(target.get("domain"))
    conf = (article.get("match") or {}).get("confidence")
    conf = float(conf) if isinstance(conf, (int, float)) else None
    if not by_domain:
        # A name can belong to several companies: without a confidence we cannot tell, so we do not show it.
        if conf is None or conf < DROP_BELOW:
            return None
    elif conf is not None and conf < DROP_BELOW:
        return None

    text = f"{title}. {article.get('description') or ''}"
    rival = target["role"] == "rival"
    adverse = kg._classify(text)
    if adverse:
        kind = {"regulatory": "regulatory", "legal": "legal", "sanctions": "regulatory", "news": "news"}[adverse]
        category, sev = "Risk", kg._severity(adverse, text)
        if rival:  # same damping as Cala screening findings about rivals
            sev = "medium" if sev == "high" else "low"
    elif _FUNDING.search(text):
        kind, category, sev = "funding", "Funding", ("medium" if rival else "info")
    elif _MNA.search(text):
        kind, category, sev = "mna", "Other", ("medium" if rival else "info")
    else:
        kind, category, sev = "news", "Other", "info"

    if conf is not None and conf < POSSIBLE_BELOW:
        status = "possible"
    elif article.get("type") == "regulatory_filing":
        status = "confirmed"
    else:
        status = "reported"

    src = article.get("source") or {}
    item = {
        "id": _id("news", article.get("story_id") or article.get("id") or url),
        "kind": kind, "category": category, "severity": sev, "status": status,
        "title": title, "body": _clip(article.get("description"), 400), "date": day,
        "company": target["company"],
        "sources": [{"name": src.get("name") or src.get("domain") or "News", "url": url, "date": day}],
        "actions": ["draft_note"], "live": True, "via": "context.dev",
    }
    if status == "possible":
        item["confidence"] = round(conf, 2)
    if target.get("subject"):
        item["subject"] = target["subject"]
    return item


def change_item(change: dict, target: dict) -> dict | None:
    """One change detected by a Context.dev page monitor -> a feed item."""
    day = _day(change.get("detected_at"))
    url = change.get("url")
    if not url or not _fresh(day, KEEP_DAYS):
        return None
    before, after = _clip(change.get("before_text_excerpt"), 160), _clip(change.get("after_text_excerpt"), 160)
    summary = _clip(change.get("summary"), 300)
    who = target["name"]
    path = urlparse(url).path.strip("/") or "site"
    title = _clip(change.get("title"), 120)
    if not title or title.lower() in ("page changed", "change detected", "content changed"):
        title = f"{who} changed its {path.split('/')[-1].replace('-', ' ')} page"
    elif who.lower() not in title.lower():
        title = f"{who}: {title}"
    body = summary
    if before and after:
        body = (body + " " if body else "") + f"Before: “{before}” Now: “{after}”"
    sev = {"high": "medium", "medium": "low"}.get((change.get("importance") or "").lower(), "info")
    host = urlparse(url).hostname or url
    item = {
        "id": _id("change", change.get("id") or f"{url}|{change.get('detected_at')}"),
        "kind": "page_change", "category": "Other", "severity": sev, "status": "confirmed",
        "title": title, "body": body, "date": day, "company": target["company"],
        "sources": [{"name": f"{re.sub(r'^www[.]', '', host)}/{path}"[:80], "url": url, "date": day}],
        "actions": ["draft_note"], "live": True, "via": "context.dev",
    }
    if before or after:
        item["before"], item["after"] = before or None, after or None
    if target.get("subject"):
        item["subject"] = target["subject"]
    return item


def _target_for_change(change: dict, targets: list[dict], mmap: dict) -> dict | None:
    by_id = {t["id"]: t for t in targets}
    cid = mmap.get(change.get("monitor_id") or "")
    if cid in by_id:
        return by_id[cid]
    host = domain_of(change.get("url"))
    if not host:
        return None
    for t in targets:
        d = t.get("domain")
        if d and (host == d or host.endswith("." + d)):
            return t
    return None


# --------------------------------------------------------------------------- sweep
async def sweep(built: dict | None, *, force: bool = False) -> dict:
    """Ask Context.dev what is new around the perimeter and store it. Returns a short report."""
    global _last_sweep
    if not ctx.enabled:
        return {"enabled": False, "new": 0}
    if not force and time.monotonic() - _last_sweep < MIN_GAP_S:
        return {"enabled": True, "new": 0, "skipped": "refreshed less than a minute ago"}
    async with _lock:
        _last_sweep = time.monotonic()
        targets = watchlist(built)
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS)).timestamp() * 1000)
        errors: list[str] = []

        async def one(t: dict) -> list[dict]:
            try:
                arts = await ctx.news(domain=t["domain"], since_ms=since_ms, limit=NEWS_LIMIT) if t["domain"] \
                    else await ctx.news(name=t["name"], since_ms=since_ms, limit=NEWS_LIMIT)
            except ContextDevError as e:
                errors.append(f"{t['name']}: {e}")
                return []
            return [i for i in (news_item(a, t) for a in arts) if i]

        found: list[dict] = [i for lst in await asyncio.gather(*[one(t) for t in targets]) for i in lst]
        try:
            mmap = monitor_map()
            for ch in await ctx.changes():
                t = _target_for_change(ch, targets, mmap)
                it = change_item(ch, t) if t else None
                if it:
                    found.append(it)
        except ContextDevError as e:
            errors.append(f"monitors: {e}")

        items: dict = LIVE.get("items") or {}
        new = 0
        # A story found for a rival and for the portfolio company itself is shown once, as the company's own.
        found.sort(key=lambda i: 0 if i.get("subject") else 1)
        for it in found:
            if it["id"] not in items:
                new += 1
                it["first_seen"] = datetime.now(timezone.utc).isoformat()
            else:
                it["first_seen"] = items[it["id"]].get("first_seen")
            items[it["id"]] = it
        LIVE["items"] = {k: v for k, v in items.items() if _fresh(v.get("date"), KEEP_DAYS)}
        LIVE["updated_at"] = datetime.now(timezone.utc).isoformat()
        LIVE["last_error"] = errors[0] if errors else None
        LIVE["targets"] = len(targets)
        save()
        log.info("live sweep: %d targets, %d items (%d new), %d errors", len(targets), len(found), new, len(errors))
        return {"enabled": True, "new": new, "items": len(LIVE["items"]), "targets": len(targets), "errors": errors[:5]}


async def loop(get_built):
    """Background task: sweep now and then every REFRESH_MIN minutes, for as long as the app runs."""
    while True:
        try:
            built = get_built()
            if built:
                await sweep(built, force=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("live sweep failed")
        await asyncio.sleep(max(1.0, REFRESH_MIN) * 60 if get_built() else 20)


# --------------------------------------------------------------------------- feed merge
def status() -> dict:
    return {"enabled": ctx.enabled, "updated_at": LIVE.get("updated_at"), "items": len(LIVE.get("items") or {}),
            "targets": LIVE.get("targets", 0), "error": LIVE.get("last_error")}


def items_for(built: dict | None) -> list[dict]:
    """Stored live items that still concern a company of the current perimeter."""
    known = {t["id"] for t in watchlist(built)}
    out = []
    for it in (LIVE.get("items") or {}).values():
        who = (it.get("subject") or it.get("company") or {}).get("id")
        if who in known and it.get("company", {}).get("id") in known and _fresh(it.get("date"), KEEP_DAYS):
            out.append({k: v for k, v in it.items() if k != "first_seen"})
    return out


def merge_feed(feed: dict, built: dict | None) -> dict:
    """Feed from Cala + live items, newest first, with the summary recounted over both."""
    extra = items_for(built)
    out = {**feed, "live": status()}
    if not extra:
        return out
    seen = {i["id"] for i in feed.get("items") or []}
    items = list(feed.get("items") or []) + [i for i in extra if i["id"] not in seen]
    items.sort(key=lambda i: (i.get("date") or "0000", _sev_rank(i["severity"])), reverse=True)
    out["items"] = items
    out["summary"] = summarize(items, len((built or {}).get("portfolio") or []))
    return out
