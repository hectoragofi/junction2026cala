# Perimeter — API contract

Perimeter: "Know first when something changes around your bets." A VC adds portfolio companies; Perimeter maps
everything around them from Cala's knowledge graph (rivals, investors, founders/people, corporate events) and shows
a sourced feed, a perimeter map, one-off company checks, and Ask. Every fact carries Cala sources.

Stack: Python 3.12 + FastAPI + uvicorn (managed with `uv`, `apps/perimeter/pyproject.toml`). Frontend: no build
step, plain HTML/CSS/ES modules in `apps/perimeter/web/`, served by FastAPI at `/`. Run:
`cd apps/perimeter && uv run uvicorn app.main:app --host 0.0.0.0 --port 8040`.
Env: `CALA_API_KEY` (from repo-root `.env` or `~/hack/.env`), `CACHE_DIR` (default `<repo>/data/cala-cache`).

## Shared types

```
Source   = { name: str, url: str|null, date: "YYYY-MM-DD"|null }
EntityRef= { id: str, name: str, type: "Company"|"Person"|"Investor"|..., sub?: str }   # sub = short descriptor
Fact     = { label: str, value: str, sources: Source[] }
```

## Endpoints (all JSON unless noted)

- `GET /api/health` → `{ok:true, cala:true}`
- `POST /api/resolve {text}` → `{ matches: [{ query, best: Company|null, candidates: Company[] }] }`
  `text` = comma/newline separated names or a URL. `Company = {id,name,description,website?,hq?,founded?}`.
- `GET /api/portfolio` → `{ companies: Company[], building: bool, built_at: iso|null }`
- `POST /api/portfolio {ids: str[]}` → saves and builds perimeter in background → `{ok:true}`
- `POST /api/portfolio/demo` → loads the preset demo portfolio (real companies) → `{ok:true}`
- `GET /api/perimeter` →
  ```
  { companies: [{ ...Company, industry?, rivals: EntityRef[], investors: (EntityRef & {shared_with?: str[]})[],
                  people: (EntityRef & {role: str, shared_with?: str[]})[] }],
    stats: { rivals, investors, people, countries, entities, facts },
    signals: [{ kind: "Board seat"|"Shared investor"|"Talent"|"M&A"|"Funding"|..., text: str,
                entities: EntityRef[], sources: Source[] }] }
  ```
  `shared_with` = names of OTHER portfolio companies or rivals the same investor/person touches (the "blue" overlap).
- `GET /api/feed` →
  ```
  { summary: str,              # e.g. "3 things need a look across your 4 companies."
    items: [{ id, kind: "overlap_investor"|"overlap_board"|"funding"|"mna"|"regulatory"|"legal"|"hiring"|"news",
              category: "Risk"|"Funding"|"Overlaps"|"Other",
              severity: "high"|"medium"|"low"|"info",
              status: "confirmed"|"reported"|"possible", confidence?: 0..1,
              title: str, body?: str, date: "YYYY-MM-DD"|null,
              company: EntityRef,           # the portfolio company it concerns
              subject?: EntityRef & {relation: str},   # e.g. {name:"Adyen", relation:"rival of Mollie"}
              sources: Source[], actions: ("draft_note")[] }] }
  ```
  Items sorted newest first; client groups by date (This week / Earlier this month / Earlier).
- `GET /api/check/stream?q=<name or entity id>` — **Server-Sent Events**:
  - `event: step` data `{key, label, status: "running"|"done"|"error", detail?: str}` keys in order:
    `match` "Matching the company", `profile` "Reading Cala profile", `people` "Mapping people and owners",
    `events` "Reading corporate events", `rivals` "Finding closest rivals", `screen` "Screening sanctions and news".
  - `event: result` data =
    ```
    { company: Company & {legal_name?, lei?, industry?, tags: str[]},
      checked_at: iso, seconds: number, period: "13 Nov 2025 – 13 Nov 2026",
      counts: {high, medium, low}, stats: {facts, entities},
      findings: [{severity, status, category, title, body, sources: Source[]}],
      sanctions: {clear: bool, screened: int, text: str, sources: Source[]},
      facts: Fact[],                         # legal name, registered in, HQ, industry, founded, LEI, website
      people: [{id,name,role, note?: str}],  # note e.g. "Also on X's board"
      ownership: [{id,name, note?: str}],
      funding: [{date, label, amount?: str, sources: Source[]}],
      rivals: [{id,name, sub?: str, in_portfolio: bool}] }
    ```
  - `event: error` data `{message}`
- `POST /api/ask {q}` → `{ answer_md: str, sources: Source[], entities: EntityRef[], seconds }` (Cala knowledge_search)
- `POST /api/draft {item_id}` → `{ subject, body }` (note to the founder about a feed item; facts + sources only)
- `GET /api/entity/{id}` → `{ id, name, type, description, facts: Fact[], relations: {[rel]: EntityRef[]} }`
  (used by source/entity popovers)
