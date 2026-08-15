// Strategy — what the agent did, after it did it.
//
// The reference screenshot reads as a planner: pick Monaco, get "Optimal Strategy,
// 89.0/100" before anything runs. SENNA has no planner and no strategy score; the agent
// decides lap by lap inside the simulator. Saad's decision (14 Aug 2026) is that this
// page is post-hoc — run it, then show the race it ran, headlined by position alone.
//
// Position alone, specifically, because summary.points is real but RL-scaled:
// terminal_points divides the FIA table by points_divisor 2.5 (configs/env.yaml:22-23),
// so a P2 finish serves 7.2 rather than 18. Showing that reads as wrong to anyone who
// knows the sport, and deriving 18 here would put a computed number on screen in a
// dashboard whose rule is that figures come from the API.

import { useState } from "react";

import { useRunFrames, useSimulation } from "../../api/queries";
import { Panel, PanelHeader } from "../../components/ui/Panel";
import RunStatusOverlay from "../../components/ui/RunStatusOverlay";
import { Stat } from "../../components/ui/Stat";
import { HonestyNote } from "../../components/ui/text";
import ViewHeader from "../../components/ui/ViewHeader";
import { EGO_CAR_ID } from "../../config/constants";
import { positiveIntParam, useWriteRunBack } from "../../lib/queryParams";
import PitSchedule from "./PitSchedule";
import RaceSetupRail from "./RaceSetupRail";
import RaceStoryChart from "./RaceStoryChart";
import StintTimeline from "./StintTimeline";
import { stintsFromFrames } from "./stints";

/** Seconds to h:mm:ss — a race time in raw seconds is unreadable at a glance. */
function raceClock(seconds: number): string {
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export default function StrategyView() {
  const [runId, setRunId] = useState<number | null>(() => positiveIntParam("run"));
  const writeRunBack = useWriteRunBack();
  const run = useSimulation(runId);
  const complete = run.data?.status === "complete";
  const frames = useRunFrames(runId, complete);

  const summary = run.data?.summary ?? null;
  const gridPosition = (run.data?.config as { grid_position?: number } | null)?.grid_position;
  const stints = stintsFromFrames(frames.data ?? [], EGO_CAR_ID);
  const dnf = summary?.dnf === true;
  // the frames land after the run row does; painting the timeline in between would show
  // a one-stint race that then rearranges itself, which reads as a bug
  const raceReadable = complete && frames.data !== undefined;
  const framesFailed = frames.isError;

  const start = () => {
    // a new run replaces what is on screen; the URL follows so the page is shareable
    return (id: number) => {
      setRunId(id);
      writeRunBack(id);
    };
  };

  return (
    <div className="flex h-full">
      <RaceSetupRail
        onRun={start()}
        currentCircuit={run.data?.circuit_id ?? null}
        currentGrid={gridPosition}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <ViewHeader>
        {runId === null && <span>no run yet — configure one on the left</span>}
        {runId !== null && (
          <>
        <span className="text-senna-muted">run {runId}</span>
        {run.data?.circuit_id != null && <span>{run.data.circuit_id.replace(/_/g, " ")}</span>}
        {run.data?.era != null && <span>era {run.data.era}</span>}
        {run.data?.model_version != null && <span>{run.data.model_version}</span>}
          </>
        )}
      </ViewHeader>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {runId === null && (
          <RunStatusOverlay
            message="no race on screen yet"
            hint="pick a circuit and a grid slot on the left, then run it — the stints, the pit schedule and the race chart all read back from what the agent actually did"
          />
        )}

        {runId !== null && !raceReadable && (
          <RunStatusOverlay
            message={
              framesFailed
                ? `run ${runId} finished, but its frames could not be loaded`
                : `run ${runId}: ${run.data?.status ?? "loading"}`
            }
            hint={
              framesFailed
                ? "the stints are read back from the stored frames — without them this page has nothing honest to draw"
                : run.data?.status === "failed"
                  ? "check the worker logs"
                  : "the worker is racing it now; the stints appear when it finishes"
            }
            failed={framesFailed || run.data?.status === "failed"}
          />
        )}

        {raceReadable && (
          <div className="flex flex-col gap-3 p-4">
            <Panel>
              <PanelHeader
                title="race strategy — as driven"
                right={summary?.race_time_s != null ? raceClock(summary.race_time_s) : undefined}
              />
              <div className="flex flex-wrap items-baseline gap-x-10 gap-y-3 p-4">
                <div data-testid="strategy-headline" className="flex items-baseline gap-3">
                  {gridPosition != null && (
                    <Stat label="grid" value={`P${gridPosition}`} className="text-senna-faint" />
                  )}
                  <span aria-hidden className="text-senna-ghost">
                    &rarr;
                  </span>
                  <Stat
                    label={dnf ? "result" : "finish"}
                    value={
                      dnf ? (
                        <span className="text-senna-danger">DNF</span>
                      ) : (
                        <span className="text-senna-accent">P{summary?.final_position}</span>
                      )
                    }
                  />
                </div>
                <Stat label="stints" value={stints.length} />
                <Stat label="stops" value={Math.max(stints.length - 1, 0)} />
                {summary?.total_laps != null && (
                  <Stat label="race laps" value={String(summary.total_laps)} />
                )}
              </div>

              <div className="px-4 pb-4">
                <StintTimeline stints={stints} />
              </div>

              {/* the race itself: where the agent came from, where the stops fell, and
                  what the safety car did to both */}
              <div className="border-t border-senna-line px-2 pb-3 pt-2">
                <RaceStoryChart frames={frames.data ?? []} egoId={EGO_CAR_ID} stints={stints} />
              </div>
            </Panel>

            <Panel>
              <PanelHeader title="pit stop schedule" />
              <PitSchedule stints={stints} />
            </Panel>

            {/* the page's 5.10.2 statement: everything above is one simulated race */}
            <HonestyNote>
              read back from run {runId}&apos;s stored frames: the agent chose these lap by lap,
              and there is no plan here that preceded the race. Pit service time is not shown
              because it is not served.
            </HonestyNote>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
