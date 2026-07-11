---
description: Merge an approved SENNA feature into main, close the branch, update the index
argument-hint: [feature-id]
---
Feature to land: $1

Preflight — abort with a clear explanation if any of these fail:
- Saad has said "approved" for this feature's ship report in this session; if he has
  not, say so and stop — /land is not a shortcut past review
- INDEX.md shows $1 as In review and you are on branch feature/$1-*
- The branch contains the latest main (rebase onto main if behind, then rerun the full
  test suite)

1. On the branch: set $1 to Done in INDEX.md with today's date, the branch name and the
   lesson link; update "Active" and "Next up". Commit `docs: close out $1`.
2. `git checkout main`, then
   `git merge --no-ff feature/$1-... -m "feat($1): <one-line summary>"`.
3. Run the full test suite once on main. Red means stop and fix before anything else.
4. Delete the feature branch locally (and on the remote if it was pushed). Push main if
   a remote exists — this will ask for permission; that is intentional.
5. Close with: one short paragraph on what SENNA can do now that it could not before,
   the suggested next feature from INDEX.md, and a reminder that the next feature gets
   a fresh session.
