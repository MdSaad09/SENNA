// View 4: the fitted tyre surface. grip over age is the served power law (T5); the
// temperature axis is a stylised illustration the fit does not actually carry, labelled
// as such (decision 1). The compound picker is gated on coverage.deg_fit, and a circuit
// with no fits gets an honest empty state rather than a broken surface. ?circuit= is
// plain view state, read off the URL as the other views read theirs.

import { OrbitControls } from "@react-three/drei";
import { useEffect, useState } from "react";

import { useCircuits, useDegradationCurves } from "../../api/queries";
import CanvasHost from "../../components/CanvasHost";
import {
  GRIP_SURFACE_RADIUS_M,
  TYRE_TEMP_AXIS_MAX_C,
  TYRE_TEMP_AXIS_MIN_C,
} from "../../config/constants";
import FitPanel from "./FitPanel";
import FitCamera from "../circuit/FitCamera";
import GripCurves from "./GripCurves";
import GripSurface from "./GripSurface";
import { useSearchParams } from "react-router-dom";
import { Panel, PanelHeader } from "../../components/ui/Panel";
import { HonestyNote } from "../../components/ui/text";
import { COMPOUND_COLOURS } from "../../config/palette";

function circuitFromLocation(): string | null {
  return new URLSearchParams(window.location.search).get("circuit");
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

export default function TyreSurfaceView() {
  const [, setSearchParams] = useSearchParams();
  const circuits = useCircuits();
  const [slug, setSlug] = useState<string | null>(circuitFromLocation);
  const [era, setEra] = useState<string | null>(null);
  const [compound, setCompound] = useState<string | null>(null);

  useEffect(() => {
    if (slug === null && circuits.data !== undefined) {
      const firstFitted = circuits.data.find((circuit) => circuit.coverage.deg_fit);
      if (firstFitted !== undefined) setSlug(firstFitted.id);
    }
  }, [slug, circuits.data]);

  const curves = useDegradationCurves(slug);
  const served = curves.data ?? [];

  const eras = unique(served.map((curve) => curve.era));
  const activeEra = era !== null && eras.includes(era) ? era : (eras[0] ?? null);
  const compounds = served.filter((curve) => curve.era === activeEra).map((curve) => curve.compound);
  const activeCompound =
    compound !== null && compounds.includes(compound) ? compound : (compounds[0] ?? null);
  const curve = served.find((c) => c.era === activeEra && c.compound === activeCompound) ?? null;
  // every compound fitted for this circuit-era, so the chart can put them side by side
  const eraCurves = served.filter((entry) => entry.era === activeEra);

  function changeCircuit(next: string) {
    setSearchParams(
      (current) => {
        current.set("circuit", next);
        return current;
      },
      { replace: true },
    );
    setSlug(next);
    setEra(null);
    setCompound(null);
  }

  const fitted = (circuits.data ?? []).filter((circuit) => circuit.coverage.deg_fit);

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-senna-line px-4 py-2 text-xs text-senna-faint">
        <label className="flex items-center gap-1">
          circuit
          <select
            value={slug ?? ""}
            onChange={(event) => changeCircuit(event.target.value)}
            className="rounded border border-senna-line bg-senna-surface px-2 py-1 text-senna-text"
          >
            {fitted.map((circuit) => (
              <option key={circuit.id} value={circuit.id}>
                {circuit.id.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        {curve !== null && (
          <>
            <label className="flex items-center gap-1">
              era
              <select
                value={activeEra ?? ""}
                onChange={(event) => setEra(event.target.value)}
                className="rounded border border-senna-line bg-senna-surface px-2 py-1 text-senna-text"
              >
                {eras.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              compound
              <select
                value={activeCompound ?? ""}
                onChange={(event) => setCompound(event.target.value)}
                className="rounded border border-senna-line bg-senna-surface px-2 py-1 text-senna-text"
              >
                {compounds.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
      <section className="relative min-h-0 min-w-0 flex-1">
        <CanvasHost>
          {curve !== null && <FitCamera radius={GRIP_SURFACE_RADIUS_M} />}
          {curve !== null && <GripSurface curve={curve} />}
          <OrbitControls makeDefault />
        </CanvasHost>

        {curves.isError && (
          <div className="absolute inset-0 grid place-items-center text-center text-sm text-senna-faint">
            <div>
              <p>no degradation fits for {(slug ?? "this circuit").replace(/_/g, " ")}</p>
              <p className="mt-1 text-xs text-senna-ghost">
                the surface needs a fitted model — run make fit after ingesting the event
              </p>
            </div>
          </div>
        )}

        {curve !== null && (
          <div className="absolute left-3 top-3 rounded-panel border border-senna-line bg-senna-surface/85 px-2 py-1 text-micro uppercase text-senna-faint">
            age {0}–{curve.cliff_age} laps &middot; temperature {TYRE_TEMP_AXIS_MIN_C}–
            {TYRE_TEMP_AXIS_MAX_C} C &middot; height is grip
          </div>
        )}
      </section>

      {eraCurves.length > 0 && (
        <aside className="flex w-96 shrink-0 flex-col gap-3 overflow-y-auto border-l border-senna-line p-3">
          <Panel>
            <PanelHeader title="grip against tyre age" right={`${eraCurves.length} compounds`} />
            <div className="p-2">
              <GripCurves curves={eraCurves} />
              <div className="mt-2 flex flex-wrap gap-3">
                {eraCurves.map((entry) => (
                  <span
                    key={entry.compound}
                    className="flex items-center gap-1.5 text-micro uppercase text-senna-faint"
                  >
                    <span
                      aria-hidden
                      className="h-2 w-2"
                      style={{ backgroundColor: COMPOUND_COLOURS[entry.compound] }}
                    />
                    {entry.compound} &middot; cliff {entry.cliff_age}
                  </span>
                ))}
              </div>
              <div className="mt-2">
                <HonestyNote>
                  the fitted decay costs only a few percent of grip across a stint — what ends a
                  stint is the dashed cliff, a failure the simulator enforces rather than a slope
                  the curve reaches. A dashed curve is a low-confidence fit.
                </HonestyNote>
              </div>
            </div>
          </Panel>

          {curve !== null && <FitPanel curve={curve} />}

          <Panel>
            <PanelHeader title="the temperature axis" />
            <div className="p-3">
              {/* decision 1: the fit is age-only, so the temperature axis is illustration */}
              <HonestyNote>
                temperature response — stylised illustration, not fitted, not a prediction; the
                T5 fit is age-only
              </HonestyNote>
            </div>
          </Panel>
        </aside>
      )}
      </div>
    </div>
  );
}
