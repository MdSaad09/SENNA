// Start a simulation to inspect or replay: the SimulationCreate form posts, the run id
// lands in ?run= so the URL survives a reload, and the caller polls until the worker is
// done. Shared by the replay and energy views — the heading and which circuits are
// offered are props; era, weather and rival band keep their 5.9.2 defaults (the full
// matrix is F13's live view).

import { useState, type FormEvent } from "react";

import { apiPost } from "../api/client";
import { useCircuits } from "../api/queries";
import type { CircuitSummary, JobAccepted } from "../api/types";

interface RunPickerProps {
  onRun: (runId: number) => void;
  heading?: string;
  includeCircuit?: (circuit: CircuitSummary) => boolean;
}

export default function RunPicker({
  onRun,
  heading = "new replay",
  includeCircuit = (circuit) => circuit.coverage.ribbon,
}: RunPickerProps) {
  const circuits = useCircuits();
  const [slug, setSlug] = useState<string | null>(null);
  // operational — a midfield default start makes the first demo run show overtakes
  const [gridPosition, setGridPosition] = useState(8);
  const [seed, setSeed] = useState<string>("");
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
      const accepted = await apiPost<JobAccepted>("/v1/simulations", {
        circuit_id: chosen,
        grid_position: gridPosition,
        ...(trimmedSeed !== "" ? { seed: Number(trimmedSeed) } : {}),
      });
      const query = new URLSearchParams(window.location.search);
      query.set("run", String(accepted.run_id));
      window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
      onRun(accepted.run_id);
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : String(thrown));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="m-auto w-80 rounded border border-neutral-800 p-4">
      <h2 className="text-sm font-semibold text-neutral-200">{heading}</h2>

      <label className="mt-3 block text-xs text-neutral-400">
        circuit
        <select
          value={chosen ?? ""}
          onChange={(event) => setSlug(event.target.value)}
          className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-200"
        >
          {offered.map((circuit) => (
            <option key={circuit.id} value={circuit.id}>
              {circuit.id.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </label>

      <label className="mt-2 block text-xs text-neutral-400">
        grid position
        <input
          type="number"
          min={1} // sourced — SimulationCreate bounds, 5.9.2 (ge=1, le=22)
          max={22}
          value={gridPosition}
          onChange={(event) => setGridPosition(Number(event.target.value))}
          className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-200"
        />
      </label>

      <label className="mt-2 block text-xs text-neutral-400">
        seed (blank draws one server-side, echoed back for reproducibility)
        <input
          type="text"
          inputMode="numeric"
          value={seed}
          onChange={(event) => setSeed(event.target.value)}
          className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-200"
        />
      </label>

      {error !== null && <p className="mt-2 text-xs text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={chosen === null || submitting}
        className="mt-4 w-full rounded border border-neutral-600 px-3 py-1.5 text-sm hover:bg-neutral-800 disabled:opacity-50"
      >
        {submitting ? "queueing" : "simulate"}
      </button>
    </form>
  );
}
