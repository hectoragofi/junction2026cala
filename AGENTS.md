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

- Everyone codes on their own machine with their own agent (Claude Code, Codex, ...). Nobody runs coding agents on
  the VPS (6 GB RAM shared by 4 people).
- `origin` is the VPS: `hack:/srv/hack/project.git` (the hackathon-vps connect script clones it for you). GitHub
  `DKeAlvaro/hackathon` is only a mirror/backup: never push there.
- One branch per task: `<user>/<feature>`; push it to `origin`. Parallel agents on one laptop: one local
  `git worktree` each (`git worktree add ../hackathon-<feature> -b <user>/<feature>`).
- Small commits with clear messages.
- Integrate into `main` often (at least every couple of hours) via a fast merge after a check;
  `git pull --rebase` before pushing `main`.
- Never force-push `main` (the server rejects it, and it cannot be deleted).
- Every push to `main` updates the live checkout `~/hack/project` on the VPS and mirrors to GitHub. The shared
  demo/backend/database runs from `~/hack/project` on the VPS (`ssh hack`, tmux or Docker). Do not edit files there:
  it is reset to `main` on every push.
- Big data and files do not go in git: use `send.sh` / `send.ps1` (they land in `~/hack/inbox/<user>/`).
- Run the app/tests before merging.
- Code freeze 3 hours before the deadline: after that only fixes and demo polish.
- Track work in `docs/tasks.md`; log choices in `docs/decisions.md`.

## Rules

- Never commit secrets: use `.env` and keep `.env.example` updated.
- Do not commit big data or models: put them in `data/` (gitignored) and move them between machines with `send.sh`.
- Bind dev servers to `0.0.0.0` on ports 3000-3999, 5000-5999 or 8000-8999.
- RAM is shared (6 GB): no huge parallel builds.
- When your context is getting full or you hand off, write a note in `docs/handoff.md`.

## Do not touch

TBD.
