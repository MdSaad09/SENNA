// View 2: replay a stored simulation run. Frames come over REST from the lap_frames
// table — the E-16 source of truth — so scrubbing is a read, never a re-simulation.
// ?run= is plain view state read off the URL (deep links with seed and circuit are
// F13's deliverable); the canvas mounts regardless, so F-28 holds on this route in
// every state. The grid size is whatever the frame says: era-2024 runs have 20 cars.

import { OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useState } from "react";

import { useCircuit, useRunFrames, useSimulation } from "../../api/queries";
import { EGO_CAR_ID } from "../../config/constants";
import CanvasHost from "../../components/CanvasHost";
import { useReplayStore } from "../../stores/replayStore";
import ReplayScene from "./ReplayScene";
import RunPicker from "./RunPicker";
import TransportControls from "./TransportControls";

function runIdFromLocation(): number | null {
  const raw = new URLSearchParams(window.location.search).get("run");
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export default function RaceReplayView() {
  const [runId, setRunId] = useState<number | null>(runIdFromLocation);
  const run = useSimulation(runId);
  const runComplete = run.data?.status === "complete";
  const frames = useRunFrames(runId, runComplete === true);
  const detail = useCircuit(run.data?.circuit_id ?? null);
  const reset = useReplayStore((state) => state.reset);
  const hudLap = useReplayStore((state) =>
    Math.min(Math.max(Math.ceil(state.playheadLap), 1), frames.data?.length ?? 1),
  );

  useEffect(() => reset(), [runId, reset]);

  const nominalLapS = run.data?.summary?.nominal_lap_s;
  const carCount = frames.data?.[0]?.cars.length;
  const agentNow = frames.data?.[hudLap - 1]?.agent;
  const ready =
    runComplete === true &&
    frames.data !== undefined &&
    frames.data.length > 0 &&
    detail.data?.gltf_url != null &&
    typeof nominalLapS === "number";

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400">
        {run.data !== undefined ? (
          <>
            <span className="text-neutral-200">
              run {run.data.run_id} — {run.data.circuit_id?.replace(/_/g, " ")}
            </span>
            <span>{run.data.status}</span>
            {carCount !== undefined && <span>{`${carCount} cars`}</span>}
            {run.data.seed !== null && <span>seed {run.data.seed}</span>}
            {run.data.model_version !== null && <span>{run.data.model_version}</span>}
            {run.data.env_config_hash !== null && <span>cfg {run.data.env_config_hash}</span>}
            {agentNow !== undefined && (
              <span className="font-mono">
                agent soc {agentNow.soc_mj.toFixed(2)} MJ · harvest{" "}
                {agentNow.harvest_mj.toFixed(2)} · deploy {agentNow.deploy_mj.toFixed(2)}
              </span>
            )}
          </>
        ) : (
          <span>no run loaded — start one below, car {EGO_CAR_ID} is the agent</span>
        )}
      </header>

      <section className="relative min-h-0 flex-1">
        <CanvasHost>
          {ready && (
            <Suspense fallback={null}>
              <ReplayScene
                detail={detail.data!}
                gltfUrl={detail.data!.gltf_url!}
                frames={frames.data!}
                nominalLapS={nominalLapS!}
              />
            </Suspense>
          )}
          <OrbitControls makeDefault />
        </CanvasHost>

        {runId === null && (
          <div className="absolute inset-0 flex">
            <RunPicker onRun={setRunId} />
          </div>
        )}
        {runId !== null && runComplete !== true && (
          <div className="absolute inset-0 grid place-items-center text-sm text-neutral-400">
            {run.data?.status === "failed"
              ? `run ${runId} failed — check the worker logs`
              : `run ${runId}: ${run.data?.status ?? "loading"}…`}
          </div>
        )}
        {runComplete === true && detail.data !== undefined && detail.data.gltf_url === null && (
          <div className="absolute inset-0 grid place-items-center text-sm text-neutral-400">
            {/* a deep-linked run on an unbuilt circuit: same honesty as View 1 (F-08) */}
            ribbon not built for {detail.data.id.replace(/_/g, " ")} — the run exists but
            cannot be drawn; run make circuits after ingesting the event
          </div>
        )}
      </section>

      {ready && frames.data !== undefined && (
        <TransportControls maxLap={frames.data[frames.data.length - 1].lap} />
      )}
    </div>
  );
}
