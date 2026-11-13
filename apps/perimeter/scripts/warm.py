"""Warm the Cala disk cache for the demo.

Builds the demo perimeter, runs company checks for the demo companies, their top rivals and a few famous
names, then rebuilds the perimeter (so rival screening, now cached, lands in the feed) and writes state.json.

    cd apps/perimeter && uv run python scripts/warm.py [--skip-checks] [extra names...]
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import main as m  # noqa: E402
from app.cala import cala  # noqa: E402
from app.check import run_check  # noqa: E402
from app.perimeter import build  # noqa: E402
from app import check as check_mod  # noqa: E402

check_mod.RIVALS_DEADLINE = check_mod.SCREEN_DEADLINE = 900.0  # warming: wait for every slow call

logging.getLogger("httpx").setLevel(logging.WARNING)

FAMOUS = ["Revolut", "Stripe", "Adyen", "Klarna", "Monzo", "N26", "Wise", "Checkout.com"]


async def check(q: str, pids: set[str], pnames: list[str]) -> str:
    t0 = time.monotonic()
    res = None
    async for ev, data in run_check(q, pids, pnames):
        if ev == "result":
            res = data
        elif ev == "error":
            return f"{q}: ERROR {data.get('message')}"
    f = res["findings"]
    return (f"{q:<22} {time.monotonic() - t0:5.1f}s  findings={len(f)} "
            f"({', '.join(x['severity'] for x in f)})  rivals={len(res['rivals'])} funding={len(res['funding'])}")


async def main():
    t0 = time.monotonic()
    extra = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = m.DEMO_PORTFOLIO
    print("building demo perimeter…", flush=True)
    res = await build(ids, progress=lambda s: print("  ·", s, f"{time.monotonic() - t0:.0f}s", cala.stats,
                                                    flush=True))
    pnames = [c["name"] for c in res["portfolio"]]
    print(f"built in {res['build_seconds']}s: {res['perimeter']['stats']}", flush=True)
    if "--skip-checks" not in sys.argv:
        rivals = []
        for c in res["perimeter"]["companies"]:
            rivals += [r["id"] for r in c["rivals"][:3]]
        targets = list(ids) + list(dict.fromkeys(rivals)) + FAMOUS + extra
        sem = asyncio.Semaphore(3)

        async def one(q):
            async with sem:
                try:
                    line = await check(q, set(ids), pnames)
                except Exception as e:
                    line = f"{q}: FAILED {e}"
                print(line, flush=True)

        await asyncio.gather(*[one(q) for q in targets])
        print("rebuilding with cached rival screening…", flush=True)
        res = await build(ids)
    m.STATE.update({"portfolio_ids": ids, "portfolio": res["portfolio"], "built": res,
                    "built_at": res["built_at"]})
    m.save_state()
    feed = res["feed"]
    print(f"\n{feed['summary']}  ({len(feed['items'])} items, {len(res['perimeter']['signals'])} signals)")
    for it in feed["items"][:25]:
        print(f"  [{it['severity']:<6}] {it.get('date') or '----------'} {it['kind']:<16} {it['title']}")
    print(f"\ntotal {time.monotonic() - t0:.0f}s  cache {cala.stats}")
    await cala.close()


if __name__ == "__main__":
    asyncio.run(main())
