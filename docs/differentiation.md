# Differentiation: why not just ChatGPT + Cala's MCP?

Working notes, not decisions. Nothing here is built or claimed on the board yet.

## The objection

Anyone can connect Cala's MCP to ChatGPT and ask the same questions. `/ask` is exactly that. More generally:
**any single-player, read-only view of Cala's data is a wrapper.** A patient agent can reproduce the feed, the map
and the check. Speed, polish, caching and diffs are convenience, not a moat.

## The test for any idea

Perimeter has to own something Cala does not have. Candidates:

- data created **between users** (responses, claims, reviews, opt-ins),
- the user's **private data** joined with the graph,
- a **track record** (dated predictions that were scored),
- **aggregate behaviour** of users (who is watching what).

## Idea 1: two-sided conflict check (the one Hector found interesting)

Both seats exist already (raising / investing) but as separate single-player views. Connect them.

1. A founder about to send a deck checks the investor. Perimeter computes the sourced paths from that fund to the
   founder's rivals (shared investors, board seats), as the overlap code does today.
2. The result is a shareable link (`/c/<id>`), not a private answer. The founder sends it to the VC: "before I share
   the data room, can you clear these?"
3. The VC responds per edge: confirmed, outdated ("we exited in 2024"), walled off ("different partner").
4. Responses are stored and shown to every later founder who checks that fund.

Why it beats the objection: it is a neutral page for two parties who do not trust each other (a chat is one
person's private session), and the responses are human-verified corrections to the graph that nobody else has.
Demo: two browser windows, one link passing between them.

Build: public page per check, respond action per edge, small response store, show prior responses on later checks.

Open question: the earlier `/investors` page was rejected. This reuses the concept (founder checks investor) as a
shared artifact instead of a dashboard. Unclear whether the concept or the page was rejected.

## More ideas

2. **Claimed pages.** Generalise idea 1: every fund and company has an auto-generated public page from Cala; the
   owner claims it and corrects edges. Owns: corrections. Weak in a demo without real owners.
3. **Predictions with a scoreboard.** Hide every deal after a cutoff date, predict from the co-investment graph
   which fund backs which company next, score against what really happened. Show the hit rate, then show live
   predictions for the portfolio's rivals. Owns: a backtested track record. Single-player, but a chat cannot show a
   number it earned. Risk: Cala's ~20 calls/min limits how big a backtest fits in the time left.
4. **Graph-verified references.** Founders leave a note on a fund ("how they behaved when a rival raised"). Only
   someone at a company the fund really backed, per Cala, can write one. Owns: reviews; the graph is the
   verification. Needs a way to prove who the writer is (work email domain matched to the company website).
5. **Conflict-free syndicate.** A founder raising gets a proposed set of investors who often co-invest and none of
   whom backs a rival; investors opt in or pass through a link. Owns: the opt-ins. Fits the "Raise backend" task
   already on the board (co-investment graph, scoring, conflict flag).
6. **Watch counts.** "9 funds started watching this company this week." Owns: aggregate attention across users.
   Honest only with real users; in a hackathon demo the numbers would be tiny.
7. **Private pipeline join.** Screen a fund's inbound deals against its portfolio. Weakest: ChatGPT with a Gmail
   connector gets close.

## Current view

Ideas 1, 4 and 5 are the same product seen from three sides: the graph as the verification layer for claims that
founders and investors make to each other. Idea 3 is a separate, single-player bet with the strongest demo number.
