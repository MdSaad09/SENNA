# SENNA — getting started from zero

One-time setup, in order. After step 7 you never do manual work again — only commands
and approvals. The day-to-day loop lives in INDEX.md under "Saad's operating manual".

1. Install the prerequisites: git, Docker Desktop, Node.js 18+, Python 3.11.
2. Install Claude Code: `npm install -g @anthropic-ai/claude-code` (see
   https://docs.claude.com/en/docs/claude-code/overview for your OS specifics), then
   run `claude` once anywhere to sign in.
3. Create an empty private GitHub repo called `senna` and clone it.
4. Copy this kit's contents into the repo root (CLAUDE.md, INDEX.md, .claude/, configs/,
   docs/, senna/, api/, frontend/, .gitignore).
5. Put the master spec PDF at `docs/spec/source/SENNA_Master_Spec_v3.pdf`.
6. Commit: `git add -A && git commit -m "chore: bootstrap senna workflow kit"` and push.
7. In the repo, run `claude`. Approve the project settings prompt if one appears
   (that loads .claude/settings.json).
8. Press Shift+Tab until the input bar shows plan mode, then type:
   `/plan-feature F00`

From here the loop is always the same:
plan mode -> /plan-feature Fxx -> read, ask, say "approved"
          -> /ship Fxx        -> read the ship report + your lesson, say "approved"
          -> /land Fxx        -> merged, branch deleted, INDEX updated
          -> close the session; new session for the next feature.

Lost? `/status`. Long session getting slow? `/compact`. Crashed? `claude --continue`.
