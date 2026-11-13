Make the shared demo on the VPS run the latest main. Arguments (optional): "$ARGUMENTS".

1. Make sure main is pushed (`git status`, `git log origin/main -1`). The VPS checkout `~/hack/project` follows origin main.
2. Read the demo start command and port from "Stack and commands" in AGENTS.md. If it is still TBD, work it out from the repo, ask the user to confirm the command and port (3000-3999, 5000-5999 or 8000-8999, bound to 0.0.0.0), then write it into AGENTS.md, commit and push main.
3. Restart the session: `ssh hack 'tmux kill-session -t demo'` (ignore "no session"), then `ssh hack "tmux new -d -s demo -c ~/hack/project '<start command>'"`.
4. Wait a few seconds, then check: `ssh hack 'curl -s -o /dev/null -w %{http_code} localhost:<port>'`. If it does not answer, read `ssh hack 'tmux capture-pane -pt demo -S -200'`, fix and retry.
5. Report the public URL `http://5.175.171.185:<port>` and the HTTP status.
