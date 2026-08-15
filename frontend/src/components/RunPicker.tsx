// Start a simulation to inspect or replay: the SimulationCreate form posts, the run id
// lands in ?run= so the URL survives a reload, and the caller polls until the worker is
// done. Shared by the replay, energy and live views — the heading and which circuits
// are offered are props. fullMatrix adds the era / weather / rival-band selects the
// 5.9.2 body accepts (F12 deferred the matrix to F13's live view; here it is).

import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { apiPost } from "../api/client";
import { useCircuits } from "../api/queries";
import type { CircuitSummary, JobAccepted, SimulationCreate } from "../api/types";
import { DEFAULT_GRID_POSITION } from "../config/constants";

interface RunPickerProps {
  onRun: (runId: number) => void;
  heading?: string;
  includeCircuit?: (circuit: CircuitSummary) => boolean;
  fullMatrix?: boolean;
}

// sourced — the SimulationCreate literals and defaults, 5.9.2 (api/schemas.py)
const ERAS = ["2026", "2024"] as const;
const WEATHER_PROFILES = ["dry", "mixed", "wet_risk"] as const;
const RIVAL_BANDS = ["test", "train"] as const;

export default function RunPicker({
  onRun,
  heading = "new replay",
  includeCircuit = (circuit) => circuit.coverage.ribbon,
  fullMatrix = false,
}: RunPickerProps) {
  const circuits = useCircuits();
  const [, setSearchParams] = useSearchParams();
  const [slug, setSlug] = useState<string | null>(null);
  const [gridPosition, setGridPosition] = useState(DEFAULT_GRID_POSITION);
  const [seed, setSeed] = useState<string>("");
  const [era, setEra] = useState<(typeof ERAS)[number]>("2026");
  const [weather, setWeather] = useState<(typeof WEATHER_PROFILES)[number]>("dry");
  const [rivalBand, setRivalBand] = useState<(typeof RIVAL_BANDS)[number]>("test");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const offered = (circuits.data ?? []).filter(includeCircuit);
  const chosen = slug ?? offered[0]?.id ?? null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen === null || submitting) return;
    const trimmedSeed = seed.trim();
    if (trimmedSeed !== "" && !/^\d+$/.test(trimmedSeed)) {
      // Number("abc") is NaN, which JSON turns into null — the server would then
      // silently draw a random seed for garbage input
      setError("seed must be a whole number, or blank");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: SimulationCreate = {
        circuit_id: chosen,
        grid_position: gridPosition,
        ...(trimmedSeed !== "" ? { seed: Number(trimmedSeed) } : {}),
        // omit the defaults so the request body stays byte-identical to F11/F12's
        // and the E-15 cache key namespace does not fork on equivalent requests
        ...(era !== "2026" ? { era } : {}),
        ...(weather !== "dry" ? { weather_profile: weather } : {}),
        ...(rivalBand !== "test" ? { rival_band: rivalBand } : {}),
      };
      const accepted = await apiPost<JobAccepted>("/v1/simulations", body);
      // through the router, not history.replaceState: a raw write is invisible to
      // useLocation, so the nav and the 5.13 jump links would keep handing on the
      // pre-run query and the next section would open its own picker
      setSearchParams(
        (current) => {
          current.set("run", String(accepted.run_id));
          return current;
        },
        { replace: true },
      );
      onRun(accepted.run_id);
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : String(thrown));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="m-auto w-80 rounded border border-senna-line p-4">
      <h2 className="text-sm font-semibold text-senna-text">{heading}</h2>

      <label className="mt-3 block text-xs text-senna-faint">
        circuit
        <select
          value={chosen ?? ""}
          onChange={(event) => setSlug(event.target.value)}
          className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
        >
          {offered.map((circuit) => (
            <option key={circuit.id} value={circuit.id}>
              {circuit.id.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </label>

      <label className="mt-2 block text-xs text-senna-faint">
        grid position
        <input
          type="number"
          min={1} // sourced — SimulationCreate bounds, 5.9.2 (ge=1, le=22)
          max={22}
          value={gridPosition}
          onChange={(event) => setGridPosition(Number(event.target.value))}
          className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
        />
      </label>

      <label className="mt-2 block text-xs text-senna-faint">
        seed (blank draws one server-side, echoed back for reproducibility)
        <input
          type="text"
          inputMode="numeric"
          value={seed}
          onChange={(event) => setSeed(event.target.value)}
          className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
        />
      </label>

      {fullMatrix && (
        <>
          <label className="mt-2 block text-xs text-senna-faint">
            era
            <select
              value={era}
              onChange={(event) => setEra(event.target.value as (typeof ERAS)[number])}
              className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
            >
              {ERAS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-2 block text-xs text-senna-faint">
            weather profile
            <select
              value={weather}
              onChange={(event) =>
                setWeather(event.target.value as (typeof WEATHER_PROFILES)[number])
              }
              className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
            >
              {WEATHER_PROFILES.map((option) => (
                <option key={option} value={option}>
                  {option.replace("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-2 block text-xs text-senna-faint">
            rival band (test = held out, the honest demo band)
            <select
              value={rivalBand}
              onChange={(event) =>
                setRivalBand(event.target.value as (typeof RIVAL_BANDS)[number])
              }
              className="mt-1 w-full rounded border border-senna-line bg-senna-surface px-2 py-1 text-sm text-senna-text"
            >
              {RIVAL_BANDS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </>
      )}

      {error !== null && <p className="mt-2 text-xs text-senna-danger">{error}</p>}

      <button
        type="submit"
        disabled={chosen === null || submitting}
        className="mt-4 w-full rounded border border-senna-line px-3 py-1.5 text-sm hover:bg-senna-raised disabled:opacity-50"
      >
        {submitting ? "queueing" : "simulate"}
      </button>
    </form>
  );
}
