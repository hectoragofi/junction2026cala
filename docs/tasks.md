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

- [ ] Perimeter QA pass: feed rows, sources, titles, overlap explainer, skeletons, progressive loading (owner: hector, branch: hector/perimeter)
- [ ] Raise view: #/raise screen, "Raise a round" entry in Start, mock fixture (owner: hector, branch: hector/perimeter)
- [ ] Demo lock: DEMO_LOCK env so public visitors cannot reset the shared portfolio (owner: hector, branch: hector/perimeter)

## Done

- [x] Perimeter prototype: Cala-backed portfolio watch (feed, map, check, ask) (owner: hector)
