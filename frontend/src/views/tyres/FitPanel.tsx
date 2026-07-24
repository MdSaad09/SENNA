// The served fit, stated plainly: the power-law params, the support columns, and the
// confidence flag keyed on mechanism. A cluster transfer names its donor circuits; a
// thin direct fit says it is thin (2024 thin fits also carry low_confidence, so the
// discriminator is the presence of source_circuit, not the flag alone).

import type { DegradationCurve } from "../../api/types";

function confidence(curve: DegradationCurve): string {
  if (curve.source_circuit !== null) {
    const donors = curve.source_circuit
      .split(",")
      .map((slug) => slug.replace(/_/g, " "))
      .join(", ");
    return `cluster transfer (T5) — from ${donors}`;
  }
  if (curve.low_confidence) {
    return `thin fit — low confidence (n=${curve.n_laps ?? "?"}, seen to age ${
      curve.max_age_seen ?? "?"
    })`;
  }
  return "direct fit — high confidence";
}

export default function FitPanel({ curve }: { curve: DegradationCurve }) {
  return (
    <aside className="rounded border border-neutral-800 bg-neutral-900/80 p-3 text-xs text-neutral-300">
      <h3 className="font-semibold text-neutral-200">
        {curve.compound} · {curve.era} — grip(age) = 1 − a·age^b (T5)
      </h3>
      <p className="mt-1 font-mono text-neutral-300">
        a = {curve.a}, b = {curve.b}
        {curve.n_laps !== null && ` · ${curve.n_laps} laps`}
        {curve.max_age_seen !== null && ` · seen to age ${curve.max_age_seen}`} · cliff at age{" "}
        {curve.cliff_age}
      </p>
      <p data-testid="fit-confidence" className="mt-1 text-neutral-400">
        <span>{confidence(curve)}</span>
      </p>
    </aside>
  );
}
