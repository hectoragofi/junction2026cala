"""Async Context.dev client: news search and page monitors for the live part of the feed.

Cala tells us who is in the perimeter; Context.dev tells us what changed around them since.
Unlike `cala.py`, nothing here is cached forever: news and monitor changes are only useful fresh.
Reference: https://docs.context.dev (REST base https://api.context.dev/v1, bearer auth).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from . import cala as _cala  # noqa: F401  (importing it loads the shared .env files)

BASE_URL = os.environ.get("CONTEXT_DEV_URL", "https://api.context.dev/v1").rstrip("/")
MONITOR_TAG = "perimeter"


class ContextDevError(Exception):
    pass


def rows(payload: Any) -> list[dict]:
    """List endpoints wrap their rows in `data`; tolerate a bare list or a differently named key."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("data", "results", "monitors", "changes", "items"):
            v = payload.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


class ContextDev:
    def __init__(self, key: str | None = None, concurrency: int | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.key = key if key is not None else os.environ.get("CONTEXT_DEV_API_KEY", "")
        self.sem = asyncio.Semaphore(concurrency or int(os.environ.get("CONTEXT_DEV_CONCURRENCY", "8")))
        self.transport = transport
        self.client: httpx.AsyncClient | None = None
        self.stats = {"calls": 0, "errors": 0}

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=BASE_URL, transport=self.transport,
                timeout=httpx.Timeout(40.0, connect=10.0),
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            )
        return self.client

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None,
                      ok_404: bool = False) -> Any:
        if not self.key:
            raise ContextDevError("CONTEXT_DEV_API_KEY not set")
        last: Exception | None = None
        async with self.sem:
            for attempt in range(4):
                self.stats["calls"] += 1
                try:
                    r = await self._client().request(method, path, json=json, params=params)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last = e
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                if r.status_code in (429, 502, 503, 504):
                    last = ContextDevError(f"HTTP {r.status_code}")
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
                if r.status_code == 404 and ok_404:
                    return None
                if r.status_code >= 400:
                    self.stats["errors"] += 1
                    raise ContextDevError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
                if not r.content:
                    return {}
                try:
                    return r.json()
                except ValueError:
                    self.stats["errors"] += 1
                    raise ContextDevError(f"{method} {path}: response was not JSON")
        self.stats["errors"] += 1
        raise ContextDevError(f"{method} {path} failed: {last}")

    # --- news -----------------------------------------------------------------
    async def news(self, *, domain: str | None = None, name: str | None = None, since_ms: int | None = None,
                   limit: int = 10) -> list[dict]:
        """Newest articles about one company. A domain is an exact identity; a name is a looser match,
        so callers should read `match.confidence` on each article. Unknown companies return []."""
        if domain:
            entity = {"type": "domain", "domain": domain}
        elif name:
            entity = {"type": "name", "name": name}
        else:
            raise ContextDevError("news() needs a domain or a name")
        body: dict = {"searchBy": {"type": "entity", "entity": entity}, "sortBy": {"type": "newest"},
                      "limit": max(1, min(int(limit), 100))}
        if since_ms:
            body["filterBy"] = {"date": {"from": int(since_ms)}}
        return rows(await self.request("POST", "/news/search", json=body, ok_404=True))

    # --- monitors -------------------------------------------------------------
    async def create_page_monitor(self, name: str, url: str, instructions: str, *, every_minutes: int = 60,
                                  selectors: list[str] | None = None, tags: list[str] | None = None) -> dict:
        target: dict = {"type": "page", "url": url, "instructions": instructions[:2000]}
        if selectors:
            target["include_selectors"] = selectors[:50]
        body = {"name": name[:120], "target": target, "tags": [MONITOR_TAG, *(tags or [])],
                "schedule": {"type": "interval", "frequency": max(10, int(every_minutes)), "unit": "minutes"}}
        r = await self.request("POST", "/monitors", json=body)
        return r.get("data") if isinstance(r, dict) and isinstance(r.get("data"), dict) else (r or {})

    async def monitors(self) -> list[dict]:
        return rows(await self.request("GET", "/monitors", params={"tag": MONITOR_TAG, "limit": 100}))

    async def run_monitor(self, monitor_id: str) -> dict:
        return await self.request("POST", f"/monitors/{monitor_id}/run") or {}

    async def delete_monitor(self, monitor_id: str) -> dict:
        return await self.request("DELETE", f"/monitors/{monitor_id}") or {}

    async def changes(self, limit: int = 100) -> list[dict]:
        """Changes detected across every monitor of the account, newest first."""
        return rows(await self.request("GET", "/monitors/changes", params={"limit": max(1, min(int(limit), 100))}))

    # --- brand ----------------------------------------------------------------
    async def pricing_url(self, domain: str) -> str | None:
        """The pricing page a company links from its own site, if Context.dev knows one (10 credits)."""
        try:
            r = await self.request("POST", "/brand/retrieve", json={"type": "by_domain", "domain": domain})
        except ContextDevError:
            return None
        brand = (r or {}).get("brand") or {}
        return ((brand.get("links") or {}).get("pricing")) or None


ctx = ContextDev()
