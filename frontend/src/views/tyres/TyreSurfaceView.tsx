// View 4: the fitted tyre surface. grip over age is the served power law (T5); the
// temperature axis is a stylised illustration the fit does not actually carry, labelled
// as such (decision 1). The compound picker is gated on coverage.deg_fit, and a circuit
// with no fits gets an honest empty state rather than a broken surface. ?circuit= is
// plain view state, read off the URL as the other views read theirs.

import { OrbitControls } from "@react-three/drei";
import { useEffect, useState } from "react";

import { useCircuits, useDegradationCurves } from "../../api/queries";
import CanvasHost from "../../components/CanvasHost";
import { TYRE_TEMP_AXIS_MAX_C, TYRE_TEMP_AXIS_MIN_C } from "../../config/constants";
import FitPanel from "./FitPanel";
import GripSurface from "./GripSurface";
import { useSearchParams } from "react-router-dom";

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

      <section className="relative min-h-0 flex-1">
        <CanvasHost>
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
          <div className="absolute bottom-3 left-3 max-w-md">
            <FitPanel curve={curve} />
          </div>
        )}

        {curve !== null && (
          <div className="absolute right-3 top-3 max-w-xs rounded border border-senna-line bg-senna-surface/80 p-2 text-xs text-senna-muted">
            <p>
              age {0}–{curve.cliff_age} laps · temperature {TYRE_TEMP_AXIS_MIN_C}–
              {TYRE_TEMP_AXIS_MAX_C} C · height is grip
            </p>
            {/* decision 1: the fit is age-only, so the temperature axis is illustration */}
            <p className="mt-1 text-senna-faint">
              temperature response — stylised illustration, not fitted, not a prediction; the
              T5 fit is age-only
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
