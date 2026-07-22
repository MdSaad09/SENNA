# configs — the anti-black-box directory

Every number the system uses lives here, and every number carries a comment naming its
origin. Four legal origins:

- **sourced** — a document backs it; the comment cites the assumptions-register row (AR-xx)
- **fitted** — a calibration notebook produced it; the comment names the notebook
- **stylised** — an explicit presentation choice; the comment says so and the UI labels it
- **operational** — an explicit engineering default (a timeout, a page size, a poll
  cadence); the comment states the sizing rationale (added for F10, decisions log
  22 Jul 2026)

Grade C values (spec Part 8) are placeholders that MUST be verified or fitted before the
phase that consumes them. `null` means "fit me": code that reads a null constant should
fail loudly, never guess.

Change values here, never in code. If a row changes, the assumptions register in the
master spec is the paper trail.
