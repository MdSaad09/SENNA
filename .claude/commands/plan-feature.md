---
description: Plan a SENNA feature thoroughly (no code) and stop for Saad's approval
argument-hint: [feature-id e.g. F05]
---
Feature to plan: $1

You are in the planning half of SENNA's workflow. Produce a plan; write no product code.
If you are not in plan mode, behave as if you were: read-only until approval.

1. Read INDEX.md. Confirm every dependency of $1 is Done. If not, stop and tell Saad
   what has to land first.
2. Read docs/spec/features/$1-*.md in full, then every master-spec section and audit ID
   it lists under "Spec anchors". Read the root CLAUDE.md and the local CLAUDE.md of
   each directory the feature will touch. If the feature spec conflicts with the master
   spec, the master spec wins — flag the conflict in the plan.
3. Explore the existing code this feature builds on (delegate anything heavy to the
   Explore subagent) so the plan matches reality, not assumptions.
4. Write the plan with exactly these sections:
   - **Objective & spec anchors** — cite the F-xx / E-xx / A-xx rows that shaped choices
   - **Deliverables** — files created or changed, one line each on what and why
   - **Constants & configs** — every number this feature introduces: name, value,
     origin (sourced / fitted / stylised), and which yaml it lives in
   - **Tests first** — each test name and the behaviour it pins down; property tests
     called out explicitly
   - **Edge cases handled** — the relevant E-xx rows and how
   - **Acceptance checklist** — the feature spec's "done means", as checkboxes
   - **Out of scope** — nearby work deliberately NOT in this feature
   - **Questions for Saad** — only genuine blockers, each with a proposed default
5. Present the plan and STOP. Touch no files. Ask: "Approve, or what should change?"
6. Only after Saad says approved (and you are out of plan mode): save the agreed plan
   to docs/plans/$1-plan.md, set $1 to Planned in INDEX.md, commit both to main as
   `docs: plan $1`, and tell Saad the next step is `/ship $1` in this same session.
