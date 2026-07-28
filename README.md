# SENNA

A Formula 1 race-strategy engine for the 2026 regulations: a lap-level simulator
races 22 cars, a reinforcement-learning agent decides every pit stop and energy
mode, a SHAP layer explains every call, and a React dashboard shows all of it.
Built as an MSc dissertation (COMP702, University of Liverpool).

*SENNA is an unofficial project and is not associated in any way with the
Formula 1 companies, the FIA or any team.*

## See it run

    docker compose up --build     # postgres, redis, api, worker, frontend — from a clean clone
    make demo-warm                # pre-runs the demo simulations
    open "http://localhost:5173/live?circuit=bahrain_grand_prix&seed=42&lap=18&speed=30&year=2024&round=1&driver=VER"

That link opens mid-race: 22 cars on a telemetry-built track ribbon, the agent's
state of charge draining and refilling, and around lap 18 a decision card with
the SHAP drivers behind the pit call. One click to Counterfactual races the
agent against VER's actual 2024 Bahrain strategy in the same simulator; one
click to Energy shows it banking charge before an attack. The serving stack is
frozen models baked into the image — no training code runs anywhere near it.

## Why this might interest you

**The 2026 physics is corrected, from primary sources.** The regulation era this
simulates is widely misreported. The MGU-K delivers 350 kW (400 kW is the
engine); the energy store is a 4 MJ state-of-charge window, not an 8 MJ battery;
and there is no per-lap deployment cap in the 2026 rulebook — the era is
recovery-limited, with a per-circuit harvest cap. An earlier version of this
project's own spec had that wrong, and the audit trail of the corrections is
part of the repository. When the FIA refined the cap from 8 to 7 MJ in April
2026, the frozen agent was re-rolled under the tighter cap rather than silently
retrained: it loses 0.13 places and derates twice as often (`make sensitivity`).

**Compliance is structural, not learned.** Illegal actions never reach the
policy — action masks plus physics clipping give 100% regulatory legality by
construction, measured as zero coerced actions across 480 evaluation races. No
reward penalty pretends to teach the rulebook.

**Nothing is a black box.** Every constant lives in `configs/*.yaml` with a
comment naming its origin: sourced (with the document), fitted (with the
notebook), stylised, or operational. Every pit decision gets a card — top SHAP
drivers, the counterfactual flip line — and the card carries its own honesty
figure: the explaining surrogate agrees with the real network on 99.7% of pit
calls and 99.1% of energy calls, on held-out decisions.

**The results reproduce, and CI enforces it.** `make report` rebuilds the entire
evaluation chapter byte-for-byte from the committed store; the freeze chain
(model manifests, config hashes, the frozen seed manifest) is asserted by tests;
`make verify` runs both plus a link check from a clean clone, with no model, no
database and no GPU.

## The honest numbers

Eleven pre-registered metrics, frozen targets, 480 held-out paired races
(`docs/results/F14-evaluation.md` — regenerated, never hand-edited). Two met,
seven missed, three report-only. A suite where every metric passes is a suite
whose bars were set after the run.

| Result | Number | Reading |
|---|---|---|
| Position gain vs engineered baseline (M1) | +2.08 places, CI [1.71, 2.48] | met — the headline capability |
| Regulatory legality (M10) | 0 illegal, 0 snapped in 480 races | met — by construction, then measured anyway |
| Tyre failures (M9) | 37.3 per 100 races (target < 2) | missed — and it explains M1: the agent buys track position by over-running its tyres |
| Counterfactual vs real strategies (M2) | 4W/5L/1T over 10 races, p = 1.0 | an honest wash at n = 10 under a pre-registered sign test — "competitive with elite humans", not "beats" |
| Safety-car decisions (M5) | SC precision 0.942, recall 0.308; VSC recall 0.000 | the agent is blind to virtual safety cars — 311 windows, zero calls; the suspected mechanism is documented as a hypothesis, not a finding |
| Sim-to-real (M8) | 0/4 circuits within the KS bar | missed upstream: the synthetic-2026 transform runs 4–6 s fast; the held-out validation split forbids refitting on the evidence |
| Luck share (M11) | 75.8% of finishing-position variance | the novel analytics finding: most of a finish is the event draw, quantified |

The counterfactuals are era-matched (a 2026-physics agent scored on 2024 races
loses ~2.5 points to the car, not the strategy — measured, and the fine-tune
that removes the confound is `make finetune`). Sim optimism is stated where it
applies: the agent optimised the simulator it is scored in; real teams optimised
reality.

## Reproduce it

Three tiers, by what you have:

- **A clean clone, nothing else**: `make verify` — the results chapter
  regenerates byte-for-byte and the freeze chain checks out. `make report`
  rewrites it.
- **Docker**: the full serving stack and the demo, as above. The frozen models,
  surrogates and track ribbons are committed and baked in.
- **The full pipeline** (local, hours): `make ingest` (FastF1/OpenF1 into
  Postgres), `make fit`, `make synth`, `make train`, `make eval`,
  `make report`. Seeds come from the frozen manifest in `configs/seeds.yaml`;
  every result row carries the config hash and model version that produced it.
  The tagged release ships a Postgres snapshot of the ingested store
  (`data/snapshot/MANIFEST.md` holds its digest; `make restore` loads it into a
  disposable database — the guard refuses anything not named `*_test`). The
  12 GB FastF1 HTTP cache is the one artifact that stays local: `make ingest`
  rebuilds it from the public APIs.

Two results need the ingested store even at evaluation time and say so when it
is absent: the M2 counterfactual battery and its coefficient sensitivity
(`make sensitivity-m2`).

## The map

    senna/       data ingest, physics fits, synthetic-2026 generator, F1RaceEnv, training, explainability
    api/ worker/ FastAPI + WebSocket streaming; RQ worker running the frozen triplets
    frontend/    React 18 + react-three-fiber, six views
    configs/     every constant, each with a provenance comment — the anti-black-box artifact
    docs/spec/   the master specification, split per section; docs/results/ the generated evidence
    docs/demo/   the demo scripts; docs/freeze.md what the release tag pins

## Integrity

AI assistance was used in building this project and is declared per the COMP702
policy. The dissertation prose is the author's own. The metric bars above were
frozen before the runs that scored them; the misses ship with their causes.

---

*SENNA is an unofficial project and is not associated in any way with the
Formula 1 companies, the FIA or any team.*
