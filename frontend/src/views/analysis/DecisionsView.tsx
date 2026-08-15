// The decision cards of a finished run, lap by lap.
//
// The live section already streams cards as the race plays (5.13's 15-45 s beat); this
// one lets you stop and read them. Same A-03 payload, same fidelity badge, plus the two
// panels the reference faked: the real three-term reward decomposition and the real
// masked action distribution.

import { useState } from "react";

import { useDecisions, useRunFrames, useSimulation } from "../../api/queries";
import { Panel, PanelHeader } from "../../components/ui/Panel";
import RunStatusOverlay from "../../components/ui/RunStatusOverlay";
import ViewHeader from "../../components/ui/ViewHeader";
import { positiveIntParam } from "../../lib/queryParams";
import DecisionCardPanel from "../live/DecisionCardPanel";
import AlternativesPanel from "./AlternativesPanel";
import RewardPanel from "./RewardPanel";

export default function DecisionsView() {
  const runId = positiveIntParam("run");
  const run = useSimulation(runId);
  const complete = run.data?.status === "complete";
  const cards = useDecisions(runId, complete);
  const frames = useRunFrames(runId, complete);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);

  if (runId === null) {
    return (
      <div className="grid h-full place-items-center p-6">
        <RunStatusOverlay
          message="no run selected"
          hint="run a race on the strategy tab, or open this section with ?run= in the URL"
        />
      </div>
    );
  }

  const available = cards.data ?? [];
  const card = available.find((entry) => entry.lap === selectedLap) ?? available[0];
  const rewardTerms = frames.data?.find((frame) => frame.lap === card?.lap)?.agent.reward_terms;

  return (
    <div className="flex h-full flex-col">
      <ViewHeader>
        <span className="text-senna-muted">run {runId}</span>
        {run.data?.circuit_id != null && <span>{run.data.circuit_id.replace(/_/g, " ")}</span>}
        <span>{available.length} cards</span>
      </ViewHeader>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {!complete && (
          <RunStatusOverlay
            message={`run ${runId}: ${run.data?.status ?? "loading"}`}
            failed={run.data?.status === "failed"}
          />
        )}

        {/* E-15: a retrained model explains only its own runs, so an empty card set is
            an honest state rather than an error to retry */}
        {complete && available.length === 0 && (
          <RunStatusOverlay
            message={`no stored explanations for model version ${run.data?.model_version ?? "unknown"}`}
            hint="a retrained model explains only its own runs (E-15) — run make explain for this checkpoint"
          />
        )}

        {card !== undefined && (
          <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="flex min-w-0 flex-col gap-3">
              <Panel>
                <PanelHeader title="decision" right={`lap ${card.lap} · ${available.length} cards`} />
                <div className="p-3">
                  <DecisionCardPanel card={card} />
                </div>
              </Panel>
              {rewardTerms !== undefined && <RewardPanel terms={rewardTerms} />}
            </div>

            <div className="flex min-w-0 flex-col gap-3">
              <Panel>
                <PanelHeader title="laps with a card" />
                <ul className="max-h-64 overflow-y-auto p-1.5">
                  {available.map((entry) => (
                    <li key={entry.lap}>
                      <button
                        type="button"
                        onClick={() => setSelectedLap(entry.lap)}
                        className={`w-full truncate px-2 py-1 text-left text-label ${
                          entry.lap === card.lap
                            ? "bg-senna-raised text-senna-accent"
                            : "text-senna-faint hover:text-senna-muted"
                        }`}
                      >
                        lap {entry.lap} &middot; {entry.decision}
                      </button>
                    </li>
                  ))}
                </ul>
              </Panel>

              <AlternativesPanel card={card} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
