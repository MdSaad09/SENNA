// View 3: the corrected energy story for a stored run. SOC over laps against the 4 MJ
// store, and paired harvest/deploy bars against the per-circuit harvest cap — the
// fictional 4 MJ deploy plane is gone (F-02). It is 2D by choice (decision 2): the
// beat is hovering a lap, not orbiting a mesh, so there is no canvas here. ?run= is
// plain view state, read off the URL exactly as the replay view reads it.

import { useState } from "react";

import { useEnergyProfile, useSimulation } from "../../api/queries";
import RunPicker from "../../components/RunPicker";
import EnergyBarsPanel from "./EnergyBarsPanel";
import SocPanel from "./SocPanel";

function runIdFromLocation(): number | null {
  const raw = new URLSearchParams(window.location.search).get("run");
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export default function EnergyView() {
  const [runId, setRunId] = useState<number | null>(runIdFromLocation);
  const run = useSimulation(runId);
  const runComplete = run.data?.status === "complete";
  const energy = useEnergyProfile(runId, runComplete === true);

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400">
        {run.data !== undefined ? (
          <>
            <span className="text-neutral-200">
              run {run.data.run_id} — {run.data.circuit_id?.replace(/_/g, " ")}
            </span>
            <span>{run.data.status}</span>
            {run.data.model_version !== null && <span>{run.data.model_version}</span>}
          </>
        ) : (
          <span>no run loaded — start one below to see its energy trace</span>
        )}
      </header>

      <section className="relative min-h-0 flex-1 overflow-y-auto">
        {runId === null && (
          <div className="absolute inset-0 flex">
            <RunPicker onRun={setRunId} heading="energy — pick a run" />
          </div>
        )}

        {runId !== null && runComplete !== true && (
          <div className="absolute inset-0 grid place-items-center text-sm text-neutral-400">
            {run.data?.status === "failed"
              ? `run ${runId} failed — check the worker logs`
              : `run ${runId}: ${run.data?.status ?? "loading"}…`}
          </div>
        )}

        {runComplete === true && energy.data !== undefined && (
          <div className="flex h-full flex-col gap-3 p-4">
            <SocPanel profile={energy.data} />
            <EnergyBarsPanel profile={energy.data} />
            {/* F-13: the series are simulator-internal — no telemetry SOC channel exists */}
            <p className="text-xs text-neutral-500">
              modelled, calibrated to 2026 aggregate behaviour
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
