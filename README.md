# PROJECT NAME (TBD)

One-line pitch: TBD

## Quick start

Open Claude Code in this folder and type `/start` (or `/start <task>`). Agents follow the Workflow in `AGENTS.md`:
claim a task on `docs/tasks.md`, work in a worktree, `/ship` to main, `/demo` to restart the shared demo.

## Team

Alvaro, Bence, Aranguren, Hector

## How to run

TBD (see "Stack and commands" in AGENTS.md once decided).

## Where things live

- Code: everyone works in their own local clone (`hackathon`) with their own coding agent. `origin` is the VPS:
  `hack:/srv/hack/project.git` (set up by the connect script of https://github.com/DKeAlvaro/hackathon-vps).
- Live copy of `main` on the VPS: `~/hack/project` (updated on every push to `main`; the shared demo runs from there)
- Local worktrees for parallel agents: `../hackathon-<feature>` on branch `<user>/<feature>`
- Files dropped from laptops: `~/hack/inbox/<user>/` (via `send.sh` / `send.ps1`)
- Live view: the web Code/Files tools (URLs in the access repo)
- GitHub `DKeAlvaro/hackathon` is only a mirror/backup of the VPS. Do not push there.

Access and setup: https://github.com/DKeAlvaro/hackathon-vps
