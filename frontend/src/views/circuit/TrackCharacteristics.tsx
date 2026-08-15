// The reference's right-hand rail, rebuilt on data that exists.
//
// It shows DOWNFORCE 95, BRAKING 88, TRACTION 90, TOP SPEED 28 — invented scores with no
// source, and a lap record the API does not serve. What the F04 pipeline does produce is
// better and checkable: corner count, braking zones detected from telemetry speed drops,
// X-mode sections inferred from full-throttle stretches, and the per-circuit harvest cap.
//
// Several circuits listed in configs/circuits.yaml have no meta.json on disk, so every
// field here can arrive null. That is a coverage gap to state, never a zero to render —
// and the count is deliberately not written down, because a hard-coded circuit total is
// the thing E-13 asks this codebase not to acquire.

import type { CircuitDetail } from "../../api/types";
import { RIBBON_PROJECTED_FILL } from "../../config/constants";
import { Panel, PanelHeader } from "../../components/ui/Panel";
import { Stat } from "../../components/ui/Stat";
import { HonestyNote } from "../../components/ui/text";

function xmodeShare(detail: CircuitDetail): string | null {
  if (detail.xmode_sections === null || detail.lap_length_m === null) return null;
  const covered = detail.xmode_sections.reduce((total, section) => total + section.length_m, 0);
  return `${((covered / detail.lap_length_m) * 100).toFixed(0)}%`;
}

export default function TrackCharacteristics({ detail }: { detail: CircuitDetail }) {
  const share = xmodeShare(detail);
  const measured = detail.corners !== null;

  return (
    <div className="flex flex-col gap-3">
      <Panel>
        <PanelHeader title="circuit" right={detail.id.replace(/_/g, " ")} />
        <div className="grid grid-cols-2 gap-y-3 p-3">
          <Stat label="race laps" value={detail.race_laps} />
          <Stat
            label="lap length"
            value={
              detail.lap_length_m === null
                ? "—"
                : `${(detail.lap_length_m / 1000).toFixed(3)} km`
            }
          />
          <Stat label="corners" value={detail.corners?.length ?? "—"} />
          <Stat label="braking zones" value={detail.braking_zones?.length ?? "—"} />
          <Stat label="x-mode sections" value={detail.xmode_sections?.length ?? "—"} />
          {/* the harvest cap is the 2026 constraint that actually binds; there is no
              per-lap deployment cap to show beside it, and there never was */}
          <Stat label="harvest cap" value={`${detail.h_max_mj} MJ`} />
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="framing" right={`${Math.round(RIBBON_PROJECTED_FILL * 100)}%`} />
        <div className="p-3">
          <HonestyNote>
            the ribbon is framed to fill about {Math.round(RIBBON_PROJECTED_FILL * 100)}% of the
            panel, fitted to its bounding sphere rather than to the track outline — so a long,
            thin circuit sits smaller than a tightly wound one of the same lap length.
            Elevation is exaggerated and banking is a visual treatment, as the legend says.
          </HonestyNote>
        </div>
      </Panel>

      {share !== null && (
        <Panel>
          <PanelHeader title="x-mode coverage" right={share} />
          <div className="p-3">
            <HonestyNote>
              {share} of the lap sits in an inferred full-throttle stretch. X-mode sections are
              not official data — no section list has been published — so this is a reading of
              the telemetry, not a specification.
            </HonestyNote>
          </div>
        </Panel>
      )}

      {!measured && (
        <Panel>
          <PanelHeader title="no circuit metadata" />
          <div className="p-3">
            <HonestyNote>
              this circuit is in configs/circuits.yaml but has no built artifacts, so corners,
              braking zones and lap length are unknown rather than zero. Run make circuits after
              ingesting the event.
            </HonestyNote>
          </div>
        </Panel>
      )}
    </div>
  );
}
