"""Async Cala MCP client with a persistent disk cache.

Every tools/call is cached forever as one JSON file per sha256(tool + args) in CACHE_DIR.
Concurrency is bounded by a semaphore; identical in-flight calls are de-duplicated.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
PERIMETER_DIR = APP_DIR.parent
REPO_DIR = PERIMETER_DIR.parent.parent

for env in (REPO_DIR / ".env", Path.home() / "hack" / ".env"):
    if env.exists():
        load_dotenv(env, override=False)

CALA_URL = os.environ.get("CALA_URL", "https://api.cala.ai/mcp/")
CACHE_DIR = Path(os.environ.get("CACHE_DIR") or (REPO_DIR / "data" / "cala-cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CALLS_DIR = CACHE_DIR / "calls"
CALLS_DIR.mkdir(parents=True, exist_ok=True)


class CalaError(Exception):
    pass


class RateLimited(CalaError):
    pass


class Cala:
    def __init__(self, concurrency: int = int(os.environ.get("CALA_CONCURRENCY", "4"))):
        self.key = os.environ.get("CALA_API_KEY", "")
        self.sem = asyncio.Semaphore(concurrency)
        self.slow_sem = asyncio.Semaphore(int(os.environ.get("CALA_SLOW_CONCURRENCY", "2")))
        self.client: httpx.AsyncClient | None = None
        self.inflight: dict[str, asyncio.Future] = {}
        self.stats = {"hits": 0, "misses": 0, "errors": 0}

    def _client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(150.0, connect=15.0),
                headers={
                    "X-API-KEY": self.key,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
        return self.client

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    @staticmethod
    def _key(tool: str, args: dict) -> str:
        raw = tool + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def cached(self, tool: str, args: dict) -> Any | None:
        p = CALLS_DIR / f"{self._key(tool, args)}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))["result"]
            except Exception:
                return None
        return None

    async def call(self, tool: str, args: dict, *, cache: bool = True) -> Any:
        k = self._key(tool, args)
        p = CALLS_DIR / f"{k}.json"
        if cache and p.exists():
            try:
                self.stats["hits"] += 1
                return json.loads(p.read_text(encoding="utf-8"))["result"]
            except Exception:
                pass
        if k in self.inflight:
            return await asyncio.shield(self.inflight[k])
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self.inflight[k] = fut
        try:
            res = await self._call_remote(tool, args)
            if cache:
                tmp = p.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps({"tool": tool, "args": args, "at": time.time(), "result": res}, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp.replace(p)
            fut.set_result(res)
            return res
        except Exception as e:
            fut.set_exception(e)
            fut.exception()  # mark retrieved
            raise
        finally:
            self.inflight.pop(k, None)

    async def _call_remote(self, tool: str, args: dict) -> Any:
        if not self.key:
            raise CalaError("CALA_API_KEY not set")
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        last: Exception | None = None
        slow = tool.startswith("knowledge_")
        async with (self.slow_sem if slow else self.sem):
            self.stats["misses"] += 1
            for attempt in range(9):
                try:
                    r = await self._client().post(CALA_URL, json=body)
                    if r.status_code in (429, 502, 503, 504):
                        last = CalaError(f"HTTP {r.status_code}")
                        await asyncio.sleep(min(2 ** attempt, 20))
                        continue
                    r.raise_for_status()
                    return self._parse(r.text)
                except RateLimited as e:
                    last = e
                    await asyncio.sleep(min(2 * 2 ** attempt, 30) + random.random() * 2)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last = e
                    await asyncio.sleep(1.0 * (attempt + 1))
        self.stats["errors"] += 1
        raise CalaError(f"{tool} failed: {last}")

    @staticmethod
    def _parse(text: str) -> Any:
        msg = None
        t = text.strip()
        if t.startswith("{"):
            msg = json.loads(t)
        else:
            for line in t.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            msg = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
        if msg is None:
            raise CalaError("empty response")
        if "error" in msg:
            raise CalaError(str(msg["error"].get("message", msg["error"])))
        res = msg.get("result") or {}
        if res.get("isError"):
            txt = " ".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
            if "429" in txt or "rate_limit" in txt.lower() or "rate limit" in txt.lower():
                raise RateLimited(txt[:200])
            raise CalaError(txt[:300] or "tool error")
        if res.get("structuredContent") is not None:
            return res["structuredContent"]
        for c in res.get("content", []):
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except json.JSONDecodeError:
                    return {"text": c["text"]}
        return res

    # --- convenience wrappers -------------------------------------------------
    async def search(self, name: str, entity_types: list[str] | None = None) -> list[dict]:
        args: dict = {"name": name}
        if entity_types:
            args["entity_types"] = entity_types
        r = await self.call("entity_search", args)
        if isinstance(r, dict):
            return r.get("entities") or r.get("results") or []
        return r or []

    async def introspect(self, eid: str) -> dict:
        return await self.call("entity_introspection", {"entity_id": eid})

    async def retrieve(self, eid: str, properties: list[str] | None = None,
                       outgoing: dict[str, int] | None = None, incoming: dict[str, int] | None = None) -> dict:
        args: dict = {"entity_id": eid}
        if properties:
            args["properties"] = properties
        rels: dict = {}
        if outgoing:
            rels["outgoing"] = {k: {"limit": v} for k, v in outgoing.items()}
        if incoming:
            rels["incoming"] = {k: {"limit": v} for k, v in incoming.items()}
        if rels:
            args["relationships"] = rels
        return await self.call("entity_retrieval", args)

    async def query(self, text: str) -> Any:
        return await self.call("knowledge_query", {"input": text})

    async def ksearch(self, text: str) -> dict:
        return await self.call("knowledge_search", {"input": text})


cala = Cala()
