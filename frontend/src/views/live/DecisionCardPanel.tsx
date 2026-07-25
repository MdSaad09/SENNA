// One A-03 decision card, rendered verbatim: the server composed the decision line,
// the plain-language sentence, the flip probes and the honesty statement, and this
// panel adds nothing but layout. The SHAP driver bars are plain divs — the server
// already trimmed to top-5 (explain.yaml cards.top_k_drivers), so there is no
// series, no axis, nothing a chart library would earn.

import type { DecisionCard } from "../../api/types";
import { MODE_ACTION_LABELS, PIT_ACTION_LABELS } from "../../config/constants";

function DriverBars({ head, drivers }: { head: string; drivers: [string, number][] }) {
  const scale = Math.max(...drivers.map(([, shap]) => Math.abs(shap)), 1e-9);
  return (
    <ul data-testid={`card-drivers-${head}`} className="mt-1 space-y-1">
      {drivers.map(([name, shap]) => (
        <li key={name} className="flex items-center gap-2 text-xs">
          <span className="w-28 shrink-0 truncate text-neutral-400">{name}</span>
          <span className="relative h-2 flex-1">
            <span
              className="absolute inset-y-0 rounded-sm"
              style={{
                width: `${(Math.abs(shap) / scale) * 50}%`,
                // sign as direction from a centre line: pushes toward the action go
                // right, pushes away go left — the SHAP reading, not a ranking
                left: shap >= 0 ? "50%" : `${50 - (Math.abs(shap) / scale) * 50}%`,
                backgroundColor: shap >= 0 ? "#a3a3a3" : "#525252",
              }}
            />
            <span className="absolute inset-y-0 left-1/2 w-px bg-neutral-700" />
          </span>
          <span className="w-12 shrink-0 text-right font-mono text-neutral-500">
            {shap >= 0 ? "+" : ""}
            {shap.toFixed(2)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function DecisionCardPanel({ card }: { card: DecisionCard }) {
  const pitLabel = PIT_ACTION_LABELS[card.action.pit];
  const modeLabel = MODE_ACTION_LABELS[card.action.mode];
  return (
    <article className="space-y-3 rounded border border-neutral-800 p-3 text-sm">
      <header>
        <p className="font-semibold text-neutral-100">{card.decision}</p>
        <p className="mt-1 text-xs text-neutral-400">{card.plain_language}</p>
      </header>

      <section>
        <h3 className="text-xs uppercase tracking-wide text-neutral-500">
          pit call — {pitLabel} ({Math.round(card.probs.pit[card.action.pit] * 100)}%)
        </h3>
        <DriverBars head="pit" drivers={card.drivers.pit} />
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide text-neutral-500">
          energy mode — {modeLabel} ({Math.round(card.probs.mode[card.action.mode] * 100)}%)
        </h3>
        <DriverBars head="mode" drivers={card.drivers.mode} />
      </section>

      {card.flip.length > 0 && (
        <section className="text-xs text-neutral-400">
          {card.flip.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </section>
      )}

      <footer
        data-testid="card-honesty"
        className="border-t border-neutral-800 pt-2 text-xs text-neutral-500"
      >
        <p>{card.honesty.statement}</p>
        <p className="mt-1 font-mono">
          {Object.entries(card.honesty.fidelity)
            .map(([head, top1]) => `${head} ${(top1 * 100).toFixed(1)}%`)
            .join(" · ")}{" "}
          · {card.honesty.model_version}
        </p>
      </footer>
    </article>
  );
}
