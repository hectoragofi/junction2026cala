Start work on a task. Task given by the user: "$ARGUMENTS" (may be empty).

Follow the "Workflow" section of AGENTS.md exactly.

1. Read `git config hackathon.user` (if empty, ask the user for their name and set it).
2. Sync: `git pull --rebase origin main` in the main clone. Read `docs/tasks.md` and the latest entries of `docs/handoff.md`.
3. If a task was given: find it on the board. If it is not there, add it to Todo. If it is already in Doing with
   another owner, stop and tell the user. Otherwise claim it per AGENTS.md (move to Doing with owner and branch,
   commit `claim: <task>`, push main, retry on rejection).
4. If no task was given: propose the top 3 unclaimed Todo tasks (one line each) and ask which one. Then claim it as above.
5. Create the worktree and branch per AGENTS.md (`git worktree add ../hackathon-<slug> -b <user>/<slug> origin/main`),
   work from that folder from now on, and push the branch once (`git push -u origin <user>/<slug>`).
6. State the plan in a few lines, then start.
