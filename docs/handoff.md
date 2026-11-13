# Handoff

Add a new entry at the top each time.

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
