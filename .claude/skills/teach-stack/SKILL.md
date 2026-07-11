---
name: teach-stack
description: How to write Saad's lessons — plain-language documents that teach the tech stack and walk the actual SENNA code line by line. Use whenever producing anything in docs/learn/, at the end of every /ship, for the /teach command, and for any request like "explain this feature, file, or concept to me".
---
# Teach-stack: Saad's lesson format

Audience: Saad — smart, doing an MSc in data science, new to most of this stack (RL,
Gymnasium, SB3, FastF1, FastAPI, RQ, Postgres, React, R3F, SHAP), and building SENNA
partly to master it. Every lesson must leave him able to (a) explain the feature in a
viva and (b) modify the code without help.

Files: one lesson per feature at `docs/learn/Fxx-<slug>.md`, plus the ledger at
`docs/learn/00-curriculum.md` (table: concept | first taught in | one-line definition).
Read the ledger before writing; append to it after.

## Lesson template — these sections, this order

1. **What we built and why** — half a page, plain English, told as race strategy first
   and software second. No jargon that has not been defined yet.
2. **New ideas in this feature** — only concepts NOT already in the ledger. For each:
   what it is (two sentences), why SENNA uses it here (cite the spec ID), a mental
   model or analogy, and the smallest possible example.
3. **The code, guided** — file by file in reading order. For each file: one paragraph
   on its role, then annotated excerpts. Core domain logic — physics equations, mask
   rules, reward terms, the training loop, the SHAP pipeline — is explained line by
   line: every line gets a stated reason for existing. Boilerplate — imports, config
   plumbing, route wiring — is explained at block level in one or two honest
   sentences. Quote real code in fenced blocks with commentary between excerpts; never
   paste whole files.
4. **How it connects** — a small ASCII sketch showing where this feature sits in the
   system diagram (spec 5.1) and what flows in and out.
5. **Try it yourself** — 3 to 5 exercises against the real repo, easy to hard: change
   a config value and predict the effect, break a named test and read the failure, add
   one small thing. Each ends with "you'll know it worked when...".
6. **Check yourself** — 5 questions a supervisor or examiner might ask, answers at the
   bottom of the file, including at least one "defend this design choice" question.
7. **Ledger update** — the exact rows being added to 00-curriculum.md.

## Voice
Follow the humanizer skill: no "let's dive in", no rule-of-three padding, no fake
enthusiasm, no filler after headings. Short sentences where the idea is simple. Define
a term the first time, use it plainly after. Prefer "the battery" to "the Energy Store
subsystem" until the formal name matters. Aim for 1,500–3,000 words; a lesson longer
than that means the feature should have been split.
