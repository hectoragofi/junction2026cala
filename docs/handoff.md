# Handoff

Add a new entry at the top each time.

## 2026-11-14 - hector (ask anything)

- Done: chat-first page at `/ask` (`web/ask.html`) and `POST /api/agent` (`app/agent.py`, SSE: step / widget / done / error). Claude (`claude-opus-5-5`, low effort) calls Cala through tools (find, profile, deals, rivals, investor_overlap, research) and answers only with widgets: headline, stats, bars, timeline, list, table, path, followups.
- State: answers take 15-25 s on cached or fast Cala calls; `rivals`, `investor_overlap` and `research` can take a minute cold. `AskIn.profile` (role, my_company, portfolio, rivals) is passed to the model as context; `ask.html` reads it from `GET /api/profile` when that exists.
- Next: decide whether `/ask` becomes the front page; link it from the header nav; the earlier `/investors` page was rejected by Hector and can be removed.
- Gotchas: needs `ANTHROPIC_API_KEY` in `~/hack/.env`. Cala's search order is already relevance-ranked: do not re-sort candidates by name similarity (it picks empty duplicate records).

## 2026-11-13 - hector (investor check)

- Done: founder-side "check your investor" page at `/investors` (`web/investor.html`, `app/investor.py`): search an investor, see conflict with your rivals, deals per year, latest deals, co-investors, portfolio, and Ask (Cala knowledge search).
- State: one Cala call for the profile (~1 s cold), up to 8 more for deal details; the conflict check reuses `find_rivals`, so it is instant for cached companies and up to a minute cold.
- Next: decide whether `/investors` becomes the front page; "what happened to their bets" (follow-on rounds per portfolio company); cleaner investor search ranking.
- Gotchas: `app/diligence.py` runs the page alone on another port for local work; the page keeps "your company" and the checked list in localStorage.

## 2026-11-13 - hector

- Done: Perimeter v1 in `apps/perimeter` (FastAPI + no-build SPA) on real Cala data: feed, map/graph, check (SSE), ask, draft. Demo portfolio Mollie, Qonto, Pennylane, Pigment.
- State: demo runs on VPS port 8040 (tmux `demo`) from warm cache `~/hack/data/perimeter-cache`. Cala allows ~20 calls/min: cold builds 6-16 min, cold checks 1.5-4.5 min. Demo only cached companies (portfolio, their rivals, Revolut, Stripe, Adyen, Klarna, Monzo, N26, Wise, Checkout.com).
- Next: richer people/board data, LLM draft polish (needs ANTHROPIC_API_KEY), Brief tab.
- Gotchas: CALA_API_KEY in `~/hack/.env`; bump the import-map `?v=` in `web/index.html` when shipping frontend changes.


## <date> - <who>

- Done:
- State (what works / what is broken):
- Next step:
- Gotchas:
