// View 6: the era-matched counterfactual, split-screen (F-24). Left, the frozen
// agent's strategy; right, the driver's actual strategy replayed in the same
// simulator on the same recorded events — so the honesty header can say, exactly,
// "in-simulator comparison under stated assumptions". Both panes read one clock,
// both frame sets are stored replays over REST (E-16: the socket adds nothing for
// completed runs), and the pending-F14 clause stays on screen until the 2024
// fine-tune is real.

import { useEffect, useMemo, useRef, useState } from "react";

import { apiPost } from "../../api/client";
import { useCircuit, useRace, useRunFrames, useSimulation } from "../../api/queries";
import type { JobAccepted, SimulationResult } from "../../api/types";
import TransportControls, {
  ILLUSTRATIVE_MOTION_CAPTION,
} from "../../components/TransportControls";
import { DIVERGENCE_FLASH_MS, DIVERGENCE_FLASH_TINT } from "../../config/constants";
import { deltaSeries, findDivergenceLap } from "../../lib/divergence";
import { useReplayStore } from "../../stores/replayStore";
import CounterfactualClock from "./CounterfactualClock";
import DeltaChartPanel from "./DeltaChartPanel";
import SplitCanvas, { ScenePane } from "./SplitCanvas";

const SPLIT_CAPTION =
  `${ILLUSTRATIVE_MOTION_CAPTION}; the quality toggle has no effect on this route — ` +
  "bloom composits the root scene and the panes render scissored";

function intParam(query: URLSearchParams, name: string): number | null {
  const raw = query.get(name);
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

// seed 0 is a legal server draw (secrets.randbelow), so ?seed=0 must round-trip
function seedParam(query: URLSearchParams): number | null {
  const raw = query.get("seed");
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

const subscribeSharedPlayhead = (listener: (playheadLap: number) => void) =>
  useReplayStore.subscribe((state) => state.playheadLap, listener);

function configNumber(run: SimulationResult | undefined, key: string): number | null {
  const value = run?.config?.[key];
  return typeof value === "number" ? value : null;
}

function configString(run: SimulationResult | undefined, key: string): string | null {
  const value = run?.config?.[key];
  return typeof value === "string" ? value : null;
}

export default function CounterfactualView() {
  const [agentRunId, setAgentRunId] = useState<number | null>(() =>
    intParam(new URLSearchParams(window.location.search), "run"),
  );
  const [postedBaselineId, setPostedBaselineId] = useState<number | null>(null);
  const [postError, setPostError] = useState<string | null>(null);
  const posted = useRef(false); // refs survive StrictMode's double effect — one POST

  useEffect(() => {
    if (agentRunId !== null || posted.current) return;
    const query = new URLSearchParams(window.location.search);
    const year = intParam(query, "year");
    const round = intParam(query, "round");
    const driver = query.get("driver");
    if (year === null || round === null || driver === null) return;
    posted.current = true;
    const seed = seedParam(query);
    apiPost<JobAccepted>("/v1/counterfactuals", {
      year,
      round,
      driver,
      ...(seed !== null ? { seed } : {}),
    })
      .then((accepted) => {
        const next = new URLSearchParams(window.location.search);
        next.set("run", String(accepted.run_id));
        window.history.replaceState(null, "", `${window.location.pathname}?${next}`);
        setPostedBaselineId(accepted.baseline_run_id ?? null);
        setAgentRunId(accepted.run_id);
      })
      .catch((thrown) => {
        setPostError(thrown instanceof Error ? thrown.message : String(thrown));
      });
  }, [agentRunId]);

  const agentRun = useSimulation(agentRunId);
  const baselineRunId =
    postedBaselineId ?? configNumber(agentRun.data, "baseline_run_id");
  const baselineRun = useSimulation(baselineRunId);

  const agentComplete = agentRun.data?.status === "complete";
  const baselineComplete = baselineRun.data?.status === "complete";
  const agentFrames = useRunFrames(agentRunId, agentComplete === true);
  const baselineFrames = useRunFrames(baselineRunId, baselineComplete === true);
  const detail = useCircuit(agentRun.data?.circuit_id ?? null);

  const year = configNumber(agentRun.data, "year");
  const round = configNumber(agentRun.data, "round");
  const driver = configString(agentRun.data, "driver");
  const race = useRace(year, round);

  // arriving from another view must not inherit its playhead; and the live store's
  // selection is per-view state the panes do not share either
  useEffect(() => {
    useReplayStore.getState().reset();
  }, [agentRunId, baselineRunId]);

  const wrapper = useRef<HTMLElement>(null);
  const agentPane = useRef<HTMLDivElement | null>(null);
  const baselinePane = useRef<HTMLDivElement | null>(null);

  const comparison = useMemo(() => {
    if (agentFrames.data === undefined || baselineFrames.data === undefined) return null;
    if (agentFrames.data.length === 0 || baselineFrames.data.length === 0) return null;
    const agentLast = agentFrames.data[agentFrames.data.length - 1].lap;
    const baselineLast = baselineFrames.data[baselineFrames.data.length - 1].lap;
    return {
      divergenceLap: findDivergenceLap(agentFrames.data, baselineFrames.data),
      series: deltaSeries(agentFrames.data, baselineFrames.data),
      sharedMaxLap: Math.max(agentLast, baselineLast),
      baselineEndsLap: baselineLast < agentLast ? baselineLast : null,
    };
  }, [agentFrames.data, baselineFrames.data]);

  // the flash is the moment's punctuation, not its record — the caption and the
  // chart marker carry the divergence permanently; this only pulses the pane
  // borders when the shared playhead crosses the lap going forward
  useEffect(() => {
    const divergenceLap = comparison?.divergenceLap ?? null;
    if (divergenceLap === null) return;
    let previous = useReplayStore.getState().playheadLap;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = useReplayStore.subscribe(
      (state) => state.playheadLap,
      (playheadLap) => {
        const crossed = previous < divergenceLap && playheadLap >= divergenceLap;
        previous = playheadLap;
        if (!crossed) return;
        for (const pane of [agentPane.current, baselinePane.current]) {
          if (pane !== null) {
            pane.style.boxShadow = `inset 0 0 0 2px ${DIVERGENCE_FLASH_TINT}`;
          }
        }
        if (timer !== null) clearTimeout(timer);
        timer = setTimeout(() => {
          for (const pane of [agentPane.current, baselinePane.current]) {
            if (pane !== null) pane.style.boxShadow = "";
          }
        }, DIVERGENCE_FLASH_MS);
      },
    );
    return () => {
      unsubscribe();
      if (timer !== null) clearTimeout(timer);
    };
  }, [comparison?.divergenceLap]);

  const nominalLapS = agentRun.data?.summary?.nominal_lap_s;
  const scenesReady =
    comparison !== null &&
    detail.data?.gltf_url != null &&
    typeof nominalLapS === "number";

  const pendingModel = configString(agentRun.data, "era_matched_model");
  const realResult = race.data?.results.find((row) => row.driver_abbrev === driver);
  // the header carries claims from two responses; it appears whole or not at all,
  // so no reader ever screenshots a half-stated assumption
  const headerReady =
    agentRun.data !== undefined && (year === null || race.data !== undefined);

  const playing = useReplayStore((state) => state.playing);
  const speed = useReplayStore((state) => state.speed);
  const setPlaying = useReplayStore((state) => state.setPlaying);
  const setSpeed = useReplayStore((state) => state.setSpeed);
  const scrubTo = useReplayStore((state) => state.scrubTo);

  // a stale deep link 404s rather than resolving; the leg's row says so instead
  // of an eternal "loading" (the demo stakes itself on links that always land)
  const legLine = (label: string, query: { data?: { status: string }; isError: boolean; error: unknown }) =>
    query.isError
      ? `${label}: ${query.error instanceof Error ? query.error.message : String(query.error)}`
      : `${label}: ${query.data?.status ?? "loading"}…`;

  const waitingRows =
    agentRunId !== null && (!agentComplete || !baselineComplete) ? (
      <div className="absolute inset-0 z-20 grid place-items-center text-sm text-neutral-400">
        <div className="space-y-1 rounded border border-neutral-800 bg-neutral-950/80 p-4">
          <p>{legLine(`agent run ${agentRunId}`, agentRun)}</p>
          {baselineRunId !== null && (
            <p>{legLine(`baseline run ${baselineRunId}`, baselineRun)}</p>
          )}
        </div>
      </div>
    ) : null;

  return (
    <div className="flex h-full flex-col">
      {headerReady && agentRun.data !== undefined ? (
        <header
          data-testid="counterfactual-honesty"
          className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400"
        >
          <span className="text-neutral-200">
            {race.data !== undefined && year !== null
              ? `${race.data.event_name} ${year}, round ${round} — ${driver}`
              : "counterfactual"}
          </span>
          <span>in-simulator comparison under stated assumptions</span>
          <span>
            {agentRun.data.era} physics
            {typeof agentRun.data.summary?.n_cars === "number" &&
              `, ${agentRun.data.summary.n_cars}-car grid`}
            {" · model "}
            {agentRun.data.model_version}
            {pendingModel === "pending-F14"
              ? " (frozen 2026) — era-matched fine-tune pending-F14"
              : pendingModel !== null && ` — era-matched model ${pendingModel}`}
          </span>
          {realResult !== undefined && (
            <span>
              in reality {driver}{" "}
              {realResult.position !== null
                ? `finished P${realResult.position} from grid ${realResult.grid_position}`
                : (realResult.status ?? "did not finish")}
            </span>
          )}
        </header>
      ) : (
        <header className="border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400">
          counterfactual — in-simulator comparison under stated assumptions
        </header>
      )}

      <section ref={wrapper} className="relative min-h-0 flex-1">
        <SplitCanvas eventSource={wrapper} />

        <div className="pointer-events-none relative z-10 flex h-full">
          <div
            ref={agentPane}
            data-testid="pane-agent"
            className="relative min-w-0 flex-1 border-r border-neutral-800"
          >
            <p className="absolute left-2 top-2 rounded bg-neutral-950/70 px-2 py-0.5 text-xs text-neutral-300">
              SENNA agent strategy
            </p>
            {scenesReady && (
              <ScenePane
                detail={detail.data!}
                gltfUrl={detail.data!.gltf_url!}
                frames={agentFrames.data!}
                nominalLapS={nominalLapS!}
                store={useReplayStore}
                egoBadge="agent"
              />
            )}
          </div>
          <div
            ref={baselinePane}
            data-testid="pane-baseline"
            className="relative min-w-0 flex-1"
          >
            <p className="absolute left-2 top-2 rounded bg-neutral-950/70 px-2 py-0.5 text-xs text-neutral-300">
              actual {year ?? ""} strategy (replayed in-simulator)
            </p>
            {scenesReady && (
              <ScenePane
                detail={detail.data!}
                gltfUrl={detail.data!.gltf_url!}
                frames={baselineFrames.data!}
                nominalLapS={nominalLapS!}
                store={useReplayStore}
                egoBadge={null}
              />
            )}
          </div>
        </div>

        {agentRunId === null && postError === null && (
          <div className="absolute inset-0 z-20 grid place-items-center px-8 text-center text-sm text-neutral-400">
            <p>
              open a counterfactual with ?year=&round=&driver= in the URL — it enqueues
              the era-matched pair and pins the run ids here for sharing
            </p>
          </div>
        )}
        {postError !== null && (
          <div className="absolute inset-0 z-20 grid place-items-center px-8 text-sm text-neutral-400">
            {postError}
          </div>
        )}
        {waitingRows}
      </section>

      {scenesReady && (
        <>
          <CounterfactualClock
            nominalLapS={nominalLapS!}
            sharedMaxLap={comparison!.sharedMaxLap}
          />
          <TransportControls
            playing={playing}
            speed={speed}
            maxLap={comparison!.sharedMaxLap}
            onPlayPause={setPlaying}
            onSpeed={setSpeed}
            onScrub={(lap) => scrubTo(lap, comparison!.sharedMaxLap)}
            subscribePlayhead={subscribeSharedPlayhead}
            caption={SPLIT_CAPTION}
          />
          <DeltaChartPanel
            series={comparison!.series}
            divergenceLap={comparison!.divergenceLap}
            baselineEndsLap={comparison!.baselineEndsLap}
          />
        </>
      )}
    </div>
  );
}
