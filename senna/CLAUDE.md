# senna/ — the Python core

Everything that thinks lives here: ingest, physics fits, the environment, training,
explainability. Rules that bite in this directory:

- Nothing pandas-shaped reachable from `F1RaceEnv.step()` — the env is numpy plus plain
  Python; the 5.6.2 throughput gate depends on it. pandas belongs in ingest and fitting.
- Constants come from `configs/*.yaml` through one loader; reading a null constant
  raises. About to type a physics number? Stop, move it to yaml with provenance.
- Randomness: every stochastic stream hangs off the seed passed to `reset()` or a fit —
  no module-level RNGs, no `np.random.*` globals (SubprocVecEnv statelessness, 5.5.5).
- FastF1 and OpenF1 calls go through `senna/data` only, cache enabled, throttled;
  nothing else in the package may import fastf1 or requests.
- Tests mirror the package: `tests/<module>/test_<file>.py`; slow and property runs
  carry pytest markers so the fast suite stays fast.
- Fitted artifacts are produced by notebooks calling importable functions from here —
  logic lives in the package, narrative lives in the notebook.
