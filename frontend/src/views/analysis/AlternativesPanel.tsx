// What else the agent could have done on this lap.
//
// The reference calls this "Alternative Strategies", ranks three candidates by score and
// captions the panel "agent beam search output will populate this panel". There is no
// beam search and no score. What does exist is better: the masked policy distribution
// the card already carries (A-03), so the alternatives are the actions the agent really
// weighed, with the illegal ones named alongside the rule that forbade them.

import type { DecisionCard } from "../../api/types";
import { Panel, PanelHeader } from "../../components/ui/Panel";
import { HonestyNote } from "../../components/ui/text";
import { MODE_ACTION_LABELS, PIT_ACTION_LABELS } from "../../config/constants";

interface HeadProps {
  head: "pit" | "mode";
  labels: string[];
  probs: number[];
  legal: boolean[];
  chosen: number;
  reasons: Record<string, string>;
}

function Head({ head, labels, probs, legal, chosen, reasons }: HeadProps) {
  const ranked = labels
    .map((label, action) => ({ label, action, prob: probs[action] ?? 0, legal: legal[action] }))
    .sort((left, right) => right.prob - left.prob);

  return (
    <section className="px-3 py-2">
      <h3 className="text-micro uppercase text-senna-faint">{head} head</h3>
      <ul data-testid={`alternatives-${head}`} className="mt-1.5 space-y-1">
        {ranked.map((option) => (
          <li
            key={option.action}
            data-action={option.action}
            className="flex items-baseline gap-2 text-label"
          >
            <span className={option.action === chosen ? "text-senna-accent" : "text-senna-ghost"}>
              {option.action === chosen ? "▸" : " "}
            </span>
            <span
              className={`flex-1 truncate ${option.legal ? "text-senna-muted" : "text-senna-ghost line-through"}`}
            >
              {option.label}
            </span>
            {option.legal ? (
              <span className="w-12 shrink-0 text-right text-senna-text">
                {(option.prob * 100).toFixed(1)}%
              </span>
            ) : (
              <span className="shrink-0 text-micro uppercase text-senna-ghost">
                {reasons[String(option.action)] ?? "masked"}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function AlternativesPanel({ card }: { card: DecisionCard }) {
  return (
    <Panel>
      <PanelHeader title="alternatives considered" right={`lap ${card.lap}`} />
      <Head
        head="pit"
        labels={PIT_ACTION_LABELS}
        probs={card.probs.pit}
        legal={card.masks.pit}
        chosen={card.action.pit}
        reasons={card.masks.reasons}
      />
      <Head
        head="mode"
        labels={MODE_ACTION_LABELS}
        probs={card.probs.mode}
        legal={card.masks.mode}
        chosen={card.action.mode}
        reasons={card.masks.reasons}
      />
      <div className="border-t border-senna-line p-3">
        <HonestyNote>
          these are the masked policy probabilities for this one lap, not a search over whole
          strategies — the agent never enumerated a race plan. Struck-through actions were
          forbidden by the action mask, which is how compliance is achieved here: by
          construction, never by a reward penalty.
        </HonestyNote>
      </div>
    </Panel>
  );
}
