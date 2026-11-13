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

## Profiles (per browser, no sign-up)

Every browser has an anonymous profile id `pid` (`[A-Za-z0-9_-]{8,64}`, made by the web app, kept in localStorage
`perimeter-pid` and mirrored in a `pid` cookie, path `/`). Requests say who is asking and what they are viewing:

- identity: header `X-Profile: <pid>`, else query `?pid=` (EventSource), else the `pid` cookie (plain pages like `/ask`);
- view: header `X-View: demo` (or `?view=demo`, or the `pview=demo` cookie when no `X-Profile` header is sent) while
  exploring the shared demo.

Data endpoints (`/api/portfolio`, `/api/perimeter`, `/api/feed`, `/api/check/stream`, `/api/ask`, `/api/draft`,
`/api/rebuild`, `POST /api/portfolio`) read the visitor's own profile, or the **shared demo** when the pid has no
profile yet or the view is `demo`. The demo is the original global portfolio (`CACHE_DIR/state.json`), untouched.
Profiles live in `CACHE_DIR/profiles/<pid>.json` (profile) and `<pid>.state.json` (built perimeter).
`DEMO_LOCK=1` only protects the shared demo (403 on changing or rebuilding it, unless `X-Admin-Token`); a visitor's
own profile can always be changed. Cold builds share a global queue (`BUILD_SLOTS`, default 2); while waiting,
`GET /api/portfolio` has `queued: <position>`. A founder is a portfolio of one: their company, with its rivals watched.

- `GET /api/profile` → cheap, no Cala calls:
  ```
  { pid: str|null, exists: bool, viewing: "me"|"demo", demo_locked: bool,
    profile: null | { role: "founder"|"investor", name?, fund_or_company_name?, my_company?: Company,
                      portfolio_ids: str[], portfolio: Company[], watch_rivals: {id,name}[], created_at, updated_at },
    context: { role, demo: bool, my_company: {id,name}|null, portfolio: {id,name}[],
               rivals: {id,name}[], built_at } }     # compact: what the viewed space watches (read by /ask)
  ```
- `PUT /api/profile {role?, name?, fund_or_company_name?, my_company_id?, portfolio_ids?, watch_rivals?}` → creates or
  updates the caller's profile (identity from `X-Profile`/cookie), returns the same shape as `GET`. Changing companies
  starts a build. Founder: `my_company_id` (one company); switching investor → founder keeps the first company.
  `X-Profile: demo` targets the shared demo (403 when locked).
- `POST /api/profile/reset` → deletes the caller's profile and its perimeter → `{ok:true}`

## Endpoints (all JSON unless noted)

- `GET /api/health` → `{ok:true, cala:true, live: {enabled, updated_at, items, targets, error}}`
- `POST /api/resolve {text}` → `{ matches: [{ query, best: Company|null, candidates: Company[] }] }`
  `text` = comma/newline separated names or a URL. `Company = {id,name,description,website?,hq?,founded?}`.
- `GET /api/portfolio` → `{ companies: Company[], building: bool, built_at: iso|null, progress?, error?, status?: CompanyStatus[] }`
  `CompanyStatus = {id, name|null, status: "mapping"|"ready"|"rivals"}` (present only during a first build).
  **Progressive first build:** while a new portfolio builds (no finished build yet), `/api/perimeter` and `/api/feed`
  return what has landed so far with `building: true, partial: true, status: CompanyStatus[]`: each company is
  published after its first hop (profile, people, investors, events), then again with rivals; screening last.
  A rebuild of an existing portfolio keeps serving the previous build (no `partial`).
- `POST /api/portfolio {ids: str[]}` → replaces the viewed space's companies and builds in background → `{ok:true}`
  (own profile: always allowed; shared demo: 403 under `DEMO_LOCK` unless `ids` is the demo set)
- `POST /api/portfolio/demo` → makes sure the shared demo portfolio is built → `{ok:true}`
- `GET /api/perimeter` →
  ```
  { companies: [{ ...Company, industry?, rivals: EntityRef[], investors: (EntityRef & {shared_with?: str[]})[],
                  people: (EntityRef & {role: str, shared_with?: str[]})[] }],
    stats: { rivals, investors, people, countries, entities, facts },
    signals: [{ kind: "Board seat"|"Shared investor"|"Talent"|"M&A"|"Funding"|..., text: str,
                entities: EntityRef[], sources: Source[], path?: PathNode[] }] }
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
              sources: Source[], actions: ("draft_note")[],
              path?: PathNode[] }] }        # overlap items only (overlap_investor, overlap_board, hiring)
  PathNode = { entity: EntityRef & {role: "portfolio"|"shared"|"rival"},
               edge_to_next?: { label: str,              # reads left to right: "backed by", "also backs", "rival of"
                                sources: Source[],       # Cala sources for THIS edge only
                                note?: str,              # e.g. why Cala calls them rivals
                                rounds?: [{date?, round?, amount?, sources?}] } }
  ```
  `date` may be "YYYY-MM" or "YYYY" when the source only gives month/year precision.
  Titles are plain sentences ("Revolut experienced data breaches"); the subject/relation goes in `subject`.
  Screening sources are only kept when their title/URL or snippet is about the finding; pages whose headline is
  about something else are shown by domain.
  Items sorted newest first; client groups by date (Today / Yesterday / This week / Earlier this month / Earlier).
  **Live items (Context.dev).** With `CONTEXT_DEV_API_KEY` set, the response also carries
  `live: {enabled, updated_at, items, targets, error}` and the items found by the live layer (`app/live.py`), merged
  into `items` with `live: true, via: "context.dev"` and the summary recounted. They use the same shape:
  - news about a portfolio company or a rival, last `LIVE_NEWS_DAYS` days: `kind` = `news|regulatory|legal|funding|mna`;
    `status` = `confirmed` for a regulatory filing, `reported` for press, `possible` + `confidence` when the company
    was matched by name and Context.dev is not sure it is the same one (below 0.6 it is not shown at all).
    A story that only mentions the company (`match.level` other than `primary`) is never read as its risk: it is
    kept only if it is a raise or a deal, as an `info` line with `mention: true` and `subject.relation` ending in
    `mentioned` (a move in the company's market), and dropped otherwise.
  - `kind: "page_change"`: a page monitor saw a watched page change (e.g. a rival's pricing page). `status` is
    `confirmed`, `before` / `after` hold the text excerpts, the source is the page itself.
  Every live item is attached to a company of the current perimeter (`company`, plus `subject` for a rival).
  A sweep runs at startup and every `LIVE_REFRESH_MIN` minutes; `POST /api/live/refresh` runs one now (at most once
  a minute; needs `X-Admin-Token` under `DEMO_LOCK`) → `{enabled, new, items, targets, errors}`. Setup and monitors: `uv run python scripts/live.py`.
  `/api/perimeter` rivals now also carry `website?`, which the live layer uses to match news by domain.
- `GET /api/check/stream?q=<name or entity id>` — **Server-Sent Events**:
  - `event: step` data `{key, label, status: "running"|"done"|"error", detail?: str}` keys in order:
    `match` "Matching the company", `profile` "Reading Cala profile", `people` "Mapping people and owners",
    `events` "Reading corporate events", `rivals` "Finding closest rivals", `screen` "Screening sanctions and news".
  - `event: partial` data `{section, data, pending?: bool, late?: bool}`, streamed as each Cala call lands, so the
    report renders within seconds of the first entity retrieval and fills in:
    `company` (Company & {legal_name, lei, tags}) and `facts` first (no extra call), then `people` and `ownership`
    (sent at once with `pending: true` from the profile, again when person lookups / funding rounds land),
    `funding`, `screen` (`{findings, sanctions, counts, unavailable}`), `rivals` last (`late: true` if it missed
    its deadline). Steps for people/events/screen/rivals run in parallel. Calls are capped per check (~25).
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
