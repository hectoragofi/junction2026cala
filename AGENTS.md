# AGENTS.md

Single source of project rules for all coding agents and humans.

## Project

TBD (fill in during the first hour): problem, user, demo. Details in `docs/idea.md`.

## Stack and commands

TBD: install / run / test commands.

## Structure

- `apps/` application code (one subfolder per app/service)
- `scripts/` helper scripts
- `data/` local data and models, gitignored (only `.gitkeep` is tracked)
- `docs/` idea, decisions, tasks, handoff notes

## How we work

- One git worktree + branch per task: `~/hack/wt/<user>-<feature>` on branch `<user>/<feature>`.
- Small commits with clear messages.
- Integrate into `main` often (at least every couple of hours) via a quick PR or a fast merge after a check.
- Never force-push `main`.
- Run the app/tests before merging.
- Code freeze 3 hours before the deadline: after that only fixes and demo polish.
- Track work in `docs/tasks.md`; log choices in `docs/decisions.md`.

## Rules

- Never commit secrets: use `.env` and keep `.env.example` updated.
- Do not commit big data or models: put them in `data/` (gitignored).
- Bind dev servers to `0.0.0.0` on ports 3000-3999, 5000-5999 or 8000-8999.
- RAM is shared (6 GB): no huge parallel builds.
- When your context is getting full or you hand off, write a note in `docs/handoff.md`.

## Do not touch

TBD.
