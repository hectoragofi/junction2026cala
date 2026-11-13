"""Tests for the live layer. No network: Context.dev is replaced by an httpx mock transport.

    cd apps/perimeter && uv run python -m unittest discover -s tests -v

The payloads follow the field names in Context.dev's API reference; they are not recorded responses.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["CACHE_DIR"] = tempfile.mkdtemp(prefix="perimeter-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import live, main  # noqa: E402
from app.contextdev import ContextDev  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()


def iso(days_ago: float = 0) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


BUILT = {
    "portfolio": [{"id": "mollie", "name": "Mollie"}],
    "perimeter": {"companies": [{
        "id": "mollie", "name": "Mollie", "website": "https://www.mollie.com/",
        "rivals": [{"id": "adyen", "name": "Adyen", "website": "adyen.com"},
                   {"id": "paynl", "name": "Pay.nl"}],          # no website: matched by name
    }]},
    "feed": {"summary": "All quiet across your 1 companies.", "items": [
        {"id": "cala-1", "kind": "funding", "category": "Funding", "severity": "info", "status": "confirmed",
         "title": "Mollie raised €90M (Series B)", "date": "2020-09-08",
         "company": {"id": "mollie", "name": "Mollie", "type": "Company"}, "sources": [], "actions": []}]},
}
TARGETS = {t["id"]: t for t in live.watchlist(BUILT)}


def article(**kw) -> dict:
    a = {"id": "a1", "story_id": "s1", "url": "https://news.example/a1", "title": "Mollie opens a Lisbon office",
         "description": "The payments company is hiring 40 people.", "published_at": iso(0), "type": "editorial",
         "source": {"name": "Example News", "domain": "news.example"}, "match": {"level": "exact", "confidence": 0.97}}
    a.update(kw)
    return a


class Watchlist(unittest.TestCase):
    def test_portfolio_and_rivals_are_tied_to_cala_entities(self):
        self.assertEqual(set(TARGETS), {"mollie", "adyen", "paynl"})
        self.assertEqual(TARGETS["mollie"]["domain"], "mollie.com")
        self.assertEqual(TARGETS["adyen"]["domain"], "adyen.com")
        self.assertIsNone(TARGETS["paynl"]["domain"])
        self.assertEqual(TARGETS["adyen"]["subject"]["relation"], "rival of Mollie")
        self.assertEqual(TARGETS["adyen"]["company"]["id"], "mollie")


class NewsMapping(unittest.TestCase):
    def test_plain_news_about_a_portfolio_company(self):
        it = live.news_item(article(), TARGETS["mollie"])
        self.assertEqual((it["kind"], it["category"], it["severity"], it["status"]), ("news", "Other", "info", "reported"))
        self.assertEqual(it["date"], TODAY)
        self.assertEqual(it["sources"], [{"name": "Example News", "url": "https://news.example/a1", "date": TODAY}])
        self.assertNotIn("subject", it)
        self.assertNotIn("confidence", it)

    def test_regulatory_filing_is_confirmed_and_a_risk(self):
        it = live.news_item(article(title="Regulator fines Mollie €3.5 million over AML controls",
                                    type="regulatory_filing"), TARGETS["mollie"])
        self.assertEqual((it["kind"], it["category"], it["severity"], it["status"]),
                         ("regulatory", "Risk", "high", "confirmed"))

    def test_rival_funding_needs_a_look_and_names_the_rival(self):
        it = live.news_item(article(title="Adyen raises $200M in new funding round", description=""), TARGETS["adyen"])
        self.assertEqual((it["kind"], it["category"], it["severity"]), ("funding", "Funding", "medium"))
        self.assertEqual(it["company"]["id"], "mollie")
        self.assertEqual(it["subject"]["name"], "Adyen")

    def test_rival_risk_is_damped_like_cala_screening(self):
        it = live.news_item(article(title="Adyen sued over outage", description=""), TARGETS["adyen"])
        self.assertEqual((it["category"], it["severity"]), ("Risk", "low"))

    def test_name_match_with_middling_confidence_is_possible(self):
        it = live.news_item(article(match={"level": "partial", "confidence": 0.72}), TARGETS["paynl"])
        self.assertEqual(it["status"], "possible")
        self.assertEqual(it["confidence"], 0.72)

    def test_name_match_is_dropped_without_enough_confidence(self):
        self.assertIsNone(live.news_item(article(match={"confidence": 0.4}), TARGETS["paynl"]))
        self.assertIsNone(live.news_item(article(match=None), TARGETS["paynl"]))

    def test_old_or_undated_articles_are_dropped(self):
        self.assertIsNone(live.news_item(article(published_at=iso(live.NEWS_DAYS + 2)), TARGETS["mollie"]))
        self.assertIsNone(live.news_item(article(published_at=None), TARGETS["mollie"]))


class ChangeMapping(unittest.TestCase):
    CHANGE = {"id": "c1", "monitor_id": "m1", "url": "https://www.adyen.com/pricing", "title": "Page changed",
              "summary": "The entry plan price dropped.", "importance": "high", "detected_at": iso(0),
              "before_text_excerpt": "Starter €49 / seat", "after_text_excerpt": "Starter €29 / seat"}

    def test_page_change_keeps_before_and_after(self):
        t = live._target_for_change(self.CHANGE, list(TARGETS.values()), {})
        self.assertEqual(t["id"], "adyen")  # matched by the page's domain
        it = live.change_item(self.CHANGE, t)
        self.assertEqual((it["kind"], it["status"], it["severity"]), ("page_change", "confirmed", "medium"))
        self.assertEqual(it["title"], "Adyen changed its pricing page")
        self.assertIn("Before: “Starter €49 / seat” Now: “Starter €29 / seat”", it["body"])
        self.assertEqual((it["before"], it["after"]), ("Starter €49 / seat", "Starter €29 / seat"))
        self.assertEqual(it["sources"][0]["name"], "adyen.com/pricing")

    def test_page_off_the_company_domain_needs_the_monitor_map(self):
        ch = {**self.CHANGE, "url": "https://demo.example/pricing"}
        self.assertIsNone(live._target_for_change(ch, list(TARGETS.values()), {}))
        self.assertEqual(live._target_for_change(ch, list(TARGETS.values()), {"m1": "paynl"})["id"], "paynl")


class Client(unittest.TestCase):
    def test_news_request_shape_and_unknown_company(self):
        seen = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen.append((req.method, req.url.path, req.headers.get("authorization"), json.loads(req.content)))
            if b"unknown.example" in req.content:
                return httpx.Response(404, json={"error_code": "NOT_FOUND"})
            return httpx.Response(200, json={"data": [article()], "has_more": False})

        async def go():
            c = ContextDev(key="k-test", transport=httpx.MockTransport(handler))
            try:
                a = await c.news(domain="mollie.com", since_ms=1700000000000, limit=5)
                b = await c.news(name="Pay.nl")
                gone = await c.news(domain="unknown.example")
            finally:
                await c.close()
            return a, b, gone

        a, b, gone = asyncio.run(go())
        self.assertEqual((len(a), len(b), gone), (1, 1, []))
        method, path, auth, body = seen[0]
        self.assertEqual((method, path, auth), ("POST", "/v1/news/search", "Bearer k-test"))
        self.assertEqual(body, {"searchBy": {"type": "entity", "entity": {"type": "domain", "domain": "mollie.com"}},
                                "sortBy": {"type": "newest"}, "limit": 5,
                                "filterBy": {"date": {"from": 1700000000000}}})
        self.assertEqual(seen[1][3]["searchBy"]["entity"], {"type": "name", "name": "Pay.nl"})


class SweepAndFeed(unittest.TestCase):
    def setUp(self):
        self.calls = 0

        def handler(req: httpx.Request) -> httpx.Response:
            self.calls += 1
            if req.url.path == "/v1/monitors/changes":
                return httpx.Response(200, json={"data": [ChangeMapping.CHANGE]})
            body = json.loads(req.content)
            ent = body["searchBy"]["entity"]
            if ent.get("domain") == "mollie.com":
                return httpx.Response(200, json={"data": [article()]})
            if ent.get("domain") == "adyen.com":   # the same story also mentions the rival
                return httpx.Response(200, json={"data": [article(id="a9")]})
            return httpx.Response(200, json={"data": []})

        self.old_ctx = live.ctx
        live.ctx = ContextDev(key="k-test", transport=httpx.MockTransport(handler))
        live.LIVE.update({"items": {}, "updated_at": None, "last_error": None, "targets": 0})
        main.STATE["built"] = BUILT

    def tearDown(self):
        asyncio.run(live.ctx.close())
        live.ctx = self.old_ctx
        main.STATE["built"] = None

    def test_sweep_stores_items_once_and_feed_shows_today_first(self):
        async def go():
            first = await live.sweep(BUILT, force=True)
            second = await live.sweep(BUILT, force=True)
            throttled = await live.sweep(BUILT)
            return first, second, throttled, await main.feed()

        first, second, throttled, feed = asyncio.run(go())
        self.assertEqual(first["new"], 2)          # one story (deduplicated by story_id) + one page change
        self.assertEqual(second["new"], 0)
        self.assertIn("skipped", throttled)
        self.assertEqual(self.calls, 8)            # 3 companies + monitor changes, twice; the third call did nothing

        kinds = [i["kind"] for i in feed["items"]]
        self.assertEqual(kinds[-1], "funding")     # the 2020 Cala fact is last
        self.assertEqual(set(kinds[:2]), {"news", "page_change"})
        self.assertEqual(feed["items"][0]["date"], TODAY)
        self.assertEqual(feed["items"][0]["kind"], "page_change")   # same day: the one that needs a look goes first
        story = next(i for i in feed["items"] if i["kind"] == "news")
        self.assertNotIn("subject", story)         # found for Mollie and for Adyen: shown as Mollie's own
        self.assertEqual(feed["summary"], "1 thing needs a look across your 1 company.")
        self.assertTrue(feed["live"]["enabled"])
        self.assertEqual(feed["live"]["items"], 2)

    def test_items_about_companies_outside_the_perimeter_are_not_shown(self):
        asyncio.run(live.sweep(BUILT, force=True))
        other = {**BUILT, "perimeter": {"companies": [{"id": "qonto", "name": "Qonto", "rivals": []}]}}
        self.assertEqual(live.items_for(other), [])
        self.assertEqual(live.merge_feed(BUILT["feed"], other)["items"], BUILT["feed"]["items"])

    def test_without_a_key_the_feed_is_untouched(self):
        live.ctx = ContextDev(key="")
        self.assertEqual(asyncio.run(live.sweep(BUILT, force=True)), {"enabled": False, "new": 0})
        feed = asyncio.run(main.feed())
        self.assertEqual(feed["items"], BUILT["feed"]["items"])
        self.assertEqual(feed["summary"], BUILT["feed"]["summary"])
        self.assertFalse(feed["live"]["enabled"])


if __name__ == "__main__":
    unittest.main()
