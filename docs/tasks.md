# Tasks

Board edited by the agents. One line per task: `- [ ] <task> (owner: <user>, branch: <user>/<slug>)`.
Todo lines have no owner. Claiming = move the line to Doing, add owner and branch, commit `claim: <task>`, push main.
Done lines: `- [x] <task> (owner: <user>)`.

## Todo

- [ ] Raise backend: co-investment graph, scoring, conflict flag, GET /api/raise, warm script (aranguren said he takes it)
- [ ] Context.dev client + news: cached client, "news" step in check, possible/confirmed status
- [ ] Context.dev monitors: pricing and fund portfolio pages, changes into feed as page_change/new_deal
- [ ] Resolve from portfolio URL via Context.dev extraction
- [ ] Submission: project name and pitch in README, contract update, 2-min video, Context.dev endpoint note

## Doing

- [ ] Profiles + onboarding: per-browser profile (role, my company, portfolio), settings page, role chooser at /, per-profile state (owner: hector, branch: hector/profile)


## Done

- [x] Investor check for founders (replaces Raise view): /investors page, /api/investor/* (owner: hector)
- [x] Perimeter QA pass: feed rows, sources, titles, overlap explainer, skeletons, progressive loading (owner: hector)
- [x] Demo lock: DEMO_LOCK=1 blocks custom portfolio/rebuild unless X-Admin-Token (owner: hector)

- [x] Perimeter prototype: Cala-backed portfolio watch (feed, map, check, ask) (owner: hector)
