# F09 — Explainability: surrogate, SHAP, decision cards

Depends on: F07
Spec anchors: 5.8 (all), F-25, A-03, A-04, 5.3.5 (agent_decisions storage)

## Goal
Every decision explained honestly: a distilled surrogate with a reported fidelity
number, exact TreeSHAP everywhere, a gradient cross-check on the true network, and the
decision-card artifact a recruiter will actually read.

## Deliverables
- Distillation: 200k (state, action-probability) pairs from eval rollouts -> one XGBoost multi-class model per action head; top-1 agreement and mean KL on held-out states; hard gate: fidelity >= 90% per head or deepen the surrogate before any explanation ships
- Exact TreeSHAP on the surrogate for every logged decision; GradientExplainer cross-check on 500 sampled decisions with the attribution rank correlation reported
- A stratified 1,024-state background set across circuits, phases and track statuses — documented, because attributions depend on it
- Counterfactual flip probes: single-feature sweeps across the physical range, recording where the action flips
- Decision cards persisted to agent_decisions (one JSONB per decision, 5.3.5): top-5 drivers, flip line, plain-language line, honesty footer carrying the fidelity badge

## Out of scope
Serving cards over the API (F10); the dashboard panel (F13).

## Constants & configs
- Fidelity threshold 0.90, background size 1024, cross-check sample 500 — sourced 5.8 — configs/explain.yaml

## Tests first
- The pipeline refuses to emit cards when fidelity is below threshold — the gate is code, not intention
- TreeSHAP additivity: attributions sum to the logit difference on sampled decisions
- A flip probe on a hand-built monotone policy finds the known threshold

## Done means
- Cards exist for every eval race of the headline model; the fidelity badge value is stored per model version
- The cross-check rank correlation is computed and written down
- shap.TreeExplainer never touches the MLP directly (F-25 — the auditor enforces this)

## Notes for the plan session
Never explain a ghost: card generation keys on model_version so retraining invalidates
old explanations (this pairs with E-15 in F10).
