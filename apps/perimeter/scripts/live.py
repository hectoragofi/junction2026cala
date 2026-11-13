"""Live layer helper (Context.dev): check the setup, run a sweep, create and trigger page monitors.

    cd apps/perimeter
    uv run python scripts/live.py status              # key, watchlist, monitors, last sweep
    uv run python scripts/live.py sweep               # one sweep now; prints what would enter the feed
    uv run python scripts/live.py monitors            # watch the pricing page of every company with a website
    uv run python scripts/live.py watch <url> <company name>   # watch any page for one company (e.g. a demo page)
    uv run python scripts/live.py run <monitor_id>    # check a monitor now instead of waiting for its schedule

Reads the perimeter from the last build (state.json in CACHE_DIR), so run it where the app runs.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import live  # noqa: E402
from app.cala import CACHE_DIR  # noqa: E402
from app.contextdev import ContextDevError, ctx  # noqa: E402

PRICING_INSTRUCTIONS = ("Report changes to plan names, prices, billing periods, free-tier limits or the features "
                        "included in each plan. Ignore layout, testimonials, logos and cookie banners.")
MONITOR_MINUTES = 60


def built() -> dict | None:
    f = CACHE_DIR / "state.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("built")


async def cmd_status(_):
    targets = live.watchlist(built())
    with_domain = sum(1 for t in targets if t["domain"])
    print(f"key set: {ctx.enabled}")
    print(f"watchlist: {len(targets)} companies ({with_domain} matched by domain, {len(targets) - with_domain} by name)")
    if not ctx.enabled:
        return
    mons = await ctx.monitors()
    print(f"monitors tagged 'perimeter': {len(mons)}")
    for m in mons:
        tgt = m.get("target") or {}
        print(f"  {m.get('id')}  {m.get('status', '?'):<8} {tgt.get('url') or m.get('name')}")
    live.load()
    print(f"last sweep: {live.LIVE.get('updated_at')}  stored items: {len(live.LIVE.get('items') or {})}")


async def cmd_sweep(_):
    live.load()
    rep = await live.sweep(built(), force=True)
    print(rep)
    for it in sorted(live.items_for(built()), key=lambda i: i["date"], reverse=True):
        who = (it.get("subject") or it["company"])["name"]
        conf = f" {it['confidence']:.0%}" if it.get("confidence") is not None else ""
        print(f"  {it['date']} [{it['severity']:<6}] {it['kind']:<11} {it['status']}{conf:<5} {who}: {it['title']}")


async def cmd_monitors(_):
    targets = [t for t in live.watchlist(built()) if t["domain"]]
    have = {(m.get("target") or {}).get("url") for m in await ctx.monitors()}
    for t in targets:
        url = await ctx.pricing_url(t["domain"])
        if not url:
            print(f"  -      {t['name']}: no pricing page known")
            continue
        if url in have:
            print(f"  kept   {t['name']}: {url}")
            continue
        try:
            m = await ctx.create_page_monitor(f"Perimeter · {t['name']} · pricing", url, PRICING_INSTRUCTIONS,
                                              every_minutes=MONITOR_MINUTES)
            print(f"  new    {t['name']}: {url}  ({m.get('id')})")
        except ContextDevError as e:
            print(f"  FAILED {t['name']}: {e}")


async def cmd_watch(args):
    if len(args) < 2:
        sys.exit("usage: live.py watch <url> <company name>")
    url, name = args[0], " ".join(args[1:]).lower()
    t = next((t for t in live.watchlist(built()) if t["name"].lower() == name), None)
    if not t:
        sys.exit(f"'{name}' is not in the perimeter. Known: " + ", ".join(x["name"] for x in live.watchlist(built())))
    m = await ctx.create_page_monitor(f"Perimeter · {t['name']} · {url}", url, PRICING_INSTRUCTIONS,
                                      every_minutes=10)
    if m.get("id"):
        live.remember_monitor(m["id"], t["id"])
    print(f"watching {url} for {t['name']}: monitor {m.get('id')}")


async def cmd_run(args):
    if not args:
        sys.exit("usage: live.py run <monitor_id>")
    print(await ctx.run_monitor(args[0]))


async def main():
    cmds = {"status": cmd_status, "sweep": cmd_sweep, "monitors": cmd_monitors, "watch": cmd_watch, "run": cmd_run}
    name = sys.argv[1] if len(sys.argv) > 1 else "status"
    if name not in cmds:
        sys.exit(__doc__)
    if name != "status" and not ctx.enabled:
        sys.exit("CONTEXT_DEV_API_KEY is not set (repo-root .env or ~/hack/.env).")
    try:
        await cmds[name](sys.argv[2:])
    finally:
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
