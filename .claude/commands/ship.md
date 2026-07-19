---
description: Build an approved SENNA feature end to end on its own branch, review it, and write Saad's lesson
argument-hint: [feature-id]
---
Feature to ship: $1

Current state:
!`git status --short --branch`

Preflight — abort with a clear explanation if any of these fail:
- docs/plans/$1-plan.md exists and INDEX.md shows $1 as Planned
- the working tree is clean and you are on main, up to date with origin (if one exists)

Then:
1. Read docs/plans/$1-plan.md, the feature spec, and
   .claude/skills/human-code/SKILL.md. Apply human-code to every line you write in
   this session.
2. `git checkout -b feature/$1-<short-slug-from-plan>`.
3. Tests first. Have the test-guardian subagent draft the plan's test list, land the
   tests, run them, and show them failing for the right reasons.
   Commit: `test($1): ...`.
4. Implement in small vertical slices until green. Every constant goes to
   configs/*.yaml with a provenance comment — an inline number is a defect. Commit each
   coherent slice with a conventional, imperative message and no attribution trailers.
5. Full gate: the entire test suite, `make lint` (ruff over the WHOLE repo, notebooks
   included — CI runs `ruff check .`, so a lint scoped to senna/tests/api hides notebook
   errors and reds CI on merge), type checks, plus any property tests the spec demands
   for this feature (e.g. the 100k-random-action legality and energy test for F05).
6. Review: run the code-reviewer subagent and the spec-auditor subagent over
   `git diff main...HEAD`. Fix every Blocker and Major. For anything you deliberately
   reject, keep a one-line reason for the ship report.
7. Lesson: run the teacher subagent to write docs/learn/$1-<slug>.md per the
   teach-stack skill and update docs/learn/00-curriculum.md.
   Commit: `docs: lesson for $1`.
8. Set $1 to In review in INDEX.md and commit that on this branch.
9. Ship report, in chat, in this order: what was built vs the plan, with any deviations
   and their reasons · test summary (counts, slowest, anything skipped) · review
   findings and how each was resolved or why rejected · the acceptance checklist,
   ticked · exact commands for Saad to try it locally · where the lesson is.
10. STOP. Do not merge and do not touch main. Saad will approve, request changes, or
    ask questions; `/land $1` is his approval button.
