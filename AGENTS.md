# AGENTS.md

Single source of project rules for all coding agents and humans. Short and imperative: follow it.

## Project

Perimeter: sourced portfolio watch for VCs on Cala's knowledge graph (feed, perimeter map, company check, ask). Details in `docs/idea.md`; API in `apps/perimeter/CONTRACT.md`.

## Stack and commands

Install: `cd apps/perimeter && uv sync`. Run: `cd apps/perimeter && set -a && . ~/hack/.env && set +a && CACHE_DIR=~/hack/data/perimeter-cache uv run uvicorn app.main:app --host 0.0.0.0 --port 8040`. Warm cache: `uv run python scripts/warm.py`. Demo port: 8040.

## Structure

- `apps/` application code (one subfolder per app/service)
- `scripts/` helper scripts
- `data/` local data and models, gitignored (only `.gitkeep` is tracked)
- `docs/` idea, decisions, tasks (the board), handoff notes
- `.claude/commands/` slash commands: `/start`, `/ship`, `/demo`

## Workflow

Every agent follows this. The slash commands `/start`, `/ship`, `/demo` run the steps below.

- **Identity.** `git config hackathon.user` is your team member's name (alvaro, bence, aranguren, hector; set by the
  connect script). If empty, ask. Below, `<user>` is that name.
- **Start of a session.** `git pull --rebase origin main`. Read `docs/tasks.md` and the latest entries of
  `docs/handoff.md`.
- **Claim before working.** In `docs/tasks.md` move the task to "Doing" with `(owner: <user>, branch: <user>/<slug>)`,
  commit `claim: <task>`, push main. If the push is rejected, `git pull --rebase origin main`, re-check the task is
  not taken, retry. This push is the lock. One task per agent at a time.
- **Work in a worktree** next to the clone: `git worktree add ../hackathon-<slug> -b <user>/<slug> origin/main`.
  Commit small and often; push the branch to origin for backup (`git push -u origin <user>/<slug>`).
- **Ship.** Rebase the branch on `origin/main`, run the checks from "Stack and commands" (if none yet, at least make
  sure it builds/starts), fast-forward/merge into main, push main (this deploys to the VPS live checkout and mirrors
  to GitHub), move the task to "Done" in `docs/tasks.md`, append a 3-5 line entry at the top of `docs/handoff.md`,
  remove the worktree (`git worktree remove ../hackathon-<slug>`).
- **VPS use.** `ssh hack '<cmd>'` to run or inspect things. The shared demo runs from `~/hack/project` in a tmux
  session named `demo`: start with `ssh hack "tmux new -d -s demo -c ~/hack/project '<start command>'"`, restart =
  `tmux kill-session -t demo` then new. Bind to 0.0.0.0 on 3000-3999, 5000-5999 or 8000-8999; URL
  `http://5.175.171.185:<port>`. Logs: `ssh hack 'tmux capture-pane -pt demo -S -200'`.
- **Secrets.** Shared secrets live in `~/hack/.env` on the VPS, never in git: `scp hack:~/hack/.env .env`.
- **Big or shared data.** `scp <file> hack:~/hack/inbox/<user>/` or `~/hack/data/`. Never git.
- **Never edit files inside `~/hack/project` on the VPS**: it is reset to main on every push.
- Never force-push main, never push to the `github` remote (mirror only), never commit secrets or big files.
- Keep `docs/tasks.md` truthful. Log choices in `docs/decisions.md`. If your context is filling up, write a handoff.
- Nobody runs coding agents on the VPS (6 GB RAM shared). Code freeze 3 hours before the deadline: only fixes and
  demo polish.

## Rules

- Never commit secrets: use `.env` and keep `.env.example` updated.
- Do not commit big data or models: put them in `data/` (gitignored).
- Bind dev servers to `0.0.0.0` on ports 3000-3999, 5000-5999 or 8000-8999.
- RAM is shared (6 GB): no huge parallel builds.

## Do not touch

TBD.
