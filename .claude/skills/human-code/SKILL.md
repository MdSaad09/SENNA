---
name: human-code
description: SENNA's code style — how to write code that reads like a careful human engineer wrote it. Use whenever writing or reviewing ANY code in this repo (Python, TypeScript, React, SQL, YAML, tests, scripts) and when writing commit messages. Load at the start of every /ship and apply throughout.
---
# Human code

The goal is code a motorsport hiring manager reads and thinks "careful engineer", not
"prompt output". That comes from restraint and intent, not tricks.

## Comments
- Comment why, never what. `# FIFO: simultaneous stops queue in pit order (E-05)` is
  good. `# loop over the cars` is a defect.
- No banner comments, no `# --- Section ---`, no step-numbered narration (`# Step 1:`).
- A tricky expression earns one short comment; obvious code earns silence.
- Spec IDs in comments are encouraged — they are this project's shared vocabulary.
- TODO only with substance: `TODO(saad): refit after AR-10 verified`. Never a bare TODO.

## Docstrings
- Public API and genuinely non-obvious functions only. One line is usually enough.
- Never restate the signature ("Args: x (int): the x"). If a docstring adds nothing a
  reader cannot already see, delete it.
- Module docstrings only where the module has a story worth telling — the env, the
  reward, the ribbon builder — not on `__init__.py` plumbing.

## Naming and units
- Domain vocabulary: stint, out_lap, undercut, soc_mj, h_max_mj, pit_loss_s, grip_est.
- Physical quantities carry units in the name: `_mj`, `_kw`, `_s`, `_kg`, `_kmh`.
- Banned names: `data`, `result`, `temp`, `helper`, `utils2`, `Manager`, `Processor`,
  `do_stuff`, and single letters outside tight math.

## Structure
- Reach for the plainest thing that works: a function over a class, a dict over a
  dataclass over a class hierarchy. Classes only for real state (the env, a fitted
  model wrapper).
- No premature abstraction: no factories, registries, or plugin systems for one caller.
  Three real call sites before generalising.
- A longer function that reads top to bottom like the physics it implements beats five
  fragments named `_do_part_2`.
- Early returns over nested else. f-strings. Type hints on public boundaries; inside
  helpers only where they genuinely clarify.

## Errors
- Handle the failures the spec names — 429s, NaT laps, missing channels, dropped
  sockets — and let genuinely unexpected ones raise loudly.
- Never `except Exception: pass`. Error messages say what happened and what to do:
  `raise IngestError(f"{event}: expected {want} sessions, loaded {got} — rerun with --resume")`.

## Texture — what actually makes code read human
- Match the file you are in. Consistency within a file beats global uniformity, and
  mild variation between modules of different ages is natural, not a bug to fix.
- Vary the rhythm: not every function needs a docstring, a log line and a typed return
  in identical order.
- No emoji anywhere — code, comments, logs, commits. No decorative box-drawing.
- Delete commented-out code; git remembers.

## Commits
- Conventional, imperative, lower-case type: `feat(env): mask slicks above wet threshold`.
- Body only when the why is not obvious from the diff; then one short paragraph, not
  bullets.
- Never any AI attribution, Co-authored-by trailers, or "generated" phrasing.

## The honesty line
This skill is about craftsmanship and readability. Saad declares AI assistance per the
COMP702 policy (spec OQ-3 / F-30) — style never changes what gets declared.
