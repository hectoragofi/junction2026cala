Ship the current task. Arguments (optional notes): "$ARGUMENTS".

Follow the "Ship" step of the Workflow section in AGENTS.md for the branch/worktree you are working in.

1. Commit any pending work on the branch. `git fetch origin` and `git rebase origin/main`; resolve conflicts carefully.
2. Run the checks from "Stack and commands" in AGENTS.md. If there are none yet, at least make sure the project builds/starts. Fix failures before going on.
3. In the main clone: `git pull --rebase origin main`, merge the branch fast-forward (or a merge commit if ff is impossible). Then in `docs/tasks.md` move the task to Done and add a 3-5 line entry at the top of `docs/handoff.md` (done, state, next step, gotchas). Commit.
4. `git push origin main` (never `github`, never force). If rejected, pull --rebase and retry. The output should say "live checkout updated".
5. Push the final branch state, then remove the worktree (`git worktree remove`).
6. Report: the new main commit (short hash + subject), and whether the demo needs a restart (yes if app code changed and a demo is running: suggest `/demo`).
