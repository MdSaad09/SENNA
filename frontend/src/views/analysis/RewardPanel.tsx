// The three reward terms, as served.
//
// The F23 reference decomposes reward into six invented headings — Tire Degradation
// Management, Fuel Load Optimisation, Weather Adaptation and so on — under a footer
// admitting the panel is a placeholder. The real reward has exactly three terms (root
// CLAUDE.md; senna/env/race_env.py:357-363) and this panel names whichever of them
// arrived, never a term the payload lacks. `total` is the sum the env appends, so it is
// the header figure rather than a fourth row.

import { Panel, PanelHeader } from "../../components/ui/Panel";
import { Meter } from "../../components/ui/Stat";
import { HonestyNote } from "../../components/ui/text";

// stylised — how each key reads in the UI. A key with no entry falls back to its own
// name, so an unexpected reward_mode degrades to something honest rather than blank.
const TERM_LABELS: Record<string, string> = {
  pace: "pace shaping",
  position: "position (potential-based)",
  terminal: "terminal points",
};

export default function RewardPanel({ terms }: { terms: Record<string, number> }) {
  const named = Object.entries(terms).filter(([key]) => key !== "total");
  const largest = Math.max(...named.map(([, value]) => Math.abs(value)), 1);
  const total = terms.total;

  return (
    <Panel>
      <PanelHeader
        title="reward decomposition"
        right={total === undefined ? undefined : `total ${total.toFixed(2)}`}
      />
      <div className="p-3">
        <ul data-testid="reward-terms">
          {named.map(([key, value]) => (
            <li key={key} data-term={key}>
              <Meter
                label={TERM_LABELS[key] ?? key}
                value={value.toFixed(3)}
                fill={Math.abs(value) / largest}
              />
            </li>
          ))}
        </ul>

        <div className="mt-3">
          <HonestyNote>
            every term the environment served for this lap, and no others — this run&apos;s reward
            has three and they are all here. Bars are scaled against the largest term on the lap
            (or against 1.0, whichever is bigger), so they compare the terms with each other
            rather than against any budget.
          </HonestyNote>
        </div>
      </div>
    </Panel>
  );
}
