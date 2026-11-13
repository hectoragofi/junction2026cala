"""Measure what Cala can give us, to decide between product ideas (see docs/differentiation.md).

Answers: how many rows a list query returns and how long it takes, how long company descriptions are,
how far back dated funding rounds go, and whether shutdowns, patents and past employers are covered.

    cd apps/perimeter && uv run python scripts/probe.py            # needs CALA_API_KEY (.env or ~/hack/.env)

Uses the normal disk cache: a line marked "cached" was not timed against Cala. About 20 calls in total.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cala import cala  # noqa: E402
from app.kg import COMPANY_TYPES, company_events, fetch_entity  # noqa: E402

QUERIES = [
    ("list by place and funding", "startups in Spain with funding between 10M and 50M euros"),
    ("list by industry and year", "European fintech companies founded in 2018"),
    ("large list", "list 200 European software startups with their description and total funding"),
    ("old rounds", "funding rounds of European fintech companies in 2014"),
    ("shutdowns", "European fintech startups that shut down, went bankrupt or were dissolved"),
    ("past employers", "founders of companies incorporated after 2020 who previously worked at Revolut"),
    ("patents", "European startups that hold patents in battery technology"),
    ("research", "companies founded by researchers from ETH Zurich"),
]
SAMPLE = 6  # companies retrieved in full to look at descriptions and funding history


async def run_query(label: str, text: str) -> list[dict]:
    was_cached = cala.cached("knowledge_query", {"input": text}) is not None
    t0 = time.time()
    try:
        r = await cala.query(text)
    except Exception as e:  # report and carry on: a failing query is itself a finding
        print(f"- {label}: FAILED ({e})")
        return []
    rows = (r or {}).get("results") or []
    ents = (r or {}).get("entities") or []
    took = "cached" if was_cached else f"{time.time() - t0:.0f}s"
    cols = ", ".join(list(rows[0].keys())[:8]) if rows and isinstance(rows[0], dict) else "-"
    print(f"- {label}: {len(rows)} rows, {len(ents)} entities, {took}. Columns: {cols}")
    return ents


async def main() -> None:
    print("## List queries")
    companies: list[dict] = []
    for label, text in QUERIES:
        ents = await run_query(label, text)
        companies += [e for e in ents if e.get("entity_type") in COMPANY_TYPES]

    seen, sample = set(), []
    for e in companies:
        if e.get("id") and e["id"] not in seen:
            seen.add(e["id"])
            sample.append(e)
    sample = sample[:SAMPLE]

    print(f"\n## Company detail ({len(sample)} companies)")
    desc_lens, first_years, round_counts = [], [], []
    for e in sample:
        try:
            ent = await fetch_entity(e["id"])
            events = await company_events(ent, cap=6)
        except Exception as ex:
            print(f"- {e.get('name')}: FAILED ({ex})")
            continue
        desc = (ent["props"].get("description") or {}).get("value") or ent.get("description") or ""
        all_dates = sorted(x["date"] for x in ent["out"].get("PARTICIPATES_IN_CORPORATE_EVENT", []) if x.get("date"))
        funding = [x for x in events if x["kind"] == "funding"]
        with_amount = sum(1 for x in funding if x.get("amount"))
        with_investors = sum(1 for x in funding if any(
            (p.get("role") or "").upper() == "INVESTOR" for p in x["participants"]))
        desc_lens.append(len(desc))
        round_counts.append(len(all_dates))
        if all_dates:
            first_years.append(int(all_dates[0][:4]))
        print(f"- {ent['name']}: description {len(desc)} chars, {len(all_dates)} dated events"
              f" ({all_dates[0][:4] if all_dates else '-'} to {all_dates[-1][:4] if all_dates else '-'}),"
              f" of the latest {len(funding)} rounds {with_amount} have an amount and {with_investors} name investors,"
              f" relations: {len(ent['out'])} out / {len(ent['inc'])} in")

    print("\n## Summary")
    if desc_lens:
        print(f"- median description length: {statistics.median(desc_lens):.0f} chars")
        print(f"- median dated events per company: {statistics.median(round_counts):.0f}")
    if first_years:
        print(f"- earliest dated event in the sample: {min(first_years)}")
    print(f"- Cala calls: {cala.stats['misses']} live, {cala.stats['hits']} cached, {cala.stats['errors']} failed")
    await cala.close()


if __name__ == "__main__":
    asyncio.run(main())
