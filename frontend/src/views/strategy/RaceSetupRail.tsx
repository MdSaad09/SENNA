// The configuration rail, always on screen.
//
// The reference keeps the circuit list, the parameters, the conditions and the grid slot
// visible at all times, and it is right to: the Strategy tab is where you set a race up
// and then read what happened, so the controls that produced the result belong beside
// it. Before this the form appeared only when no run existed and then vanished, which
// left half the page empty and no way to see what the run on screen was configured with.
//
// Every parameter shown is served: race_laps, lap_length_m, xmode_sections and h_max_mj
// come from CircuitDetail, and the option lists mirror SimulationCreate (5.9.2) exactly.

import { useEffect, useRef, useState, type FormEvent } from "react";

import { apiPost } from "../../api/client";
import { useCircuit, useCircuits } from "../../api/queries";
import type { JobAccepted, SimulationCreate } from "../../api/types";
import { MicroLabel } from "../../components/ui/text";
import { DEFAULT_GRID_POSITION } from "../../config/constants";

// sourced — the SimulationCreate literals and bounds, 5.9.2 (api/schemas.py)
const ERAS = ["2026", "2024"] as const;
const WEATHER = [
  { id: "dry", blurb: "slick compounds" },
  { id: "mixed", blurb: "variable, reactive" },
  { id: "wet_risk", blurb: "wets likely" },
] as const;
const RIVAL_BANDS = ["test", "train"] as const;
const GRID_SLOTS = 22; // 22 cars, 11 teams — never 20

interface RaceSetupRailProps {
  onRun: (runId: number) => void;
  /** the run already on screen, so the rail opens showing what produced it */
  currentCircuit?: string | null;
  currentGrid?: number;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-senna-line px-3 py-3 last:border-b-0">
      <MicroLabel>{title}</MicroLabel>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Choice({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-panel border px-2 py-1 text-label ${
        active
          ? "border-senna-accent text-senna-accent"
          : "border-senna-line text-senna-faint hover:text-senna-muted"
      }`}
    >
      {children}
    </button>
  );
}

export default function RaceSetupRail({
  onRun,
  currentCircuit = null,
  currentGrid,
}: RaceSetupRailProps) {
  const circuits = useCircuits();
  const [slug, setSlug] = useState<string | null>(currentCircuit);
  const picked = useRef(false);

  // the run row arrives after first paint, so seeding from props alone left the rail
  // describing whichever circuit happened to be first in the library while the race on
  // screen was a different one — 58 laps in the rail against 57 in the results
  useEffect(() => {
    if (!picked.current && currentCircuit !== null) setSlug(currentCircuit);
  }, [currentCircuit]);
  const [grid, setGrid] = useState(currentGrid ?? DEFAULT_GRID_POSITION);
  const [era, setEra] = useState<(typeof ERAS)[number]>("2026");
  const [weather, setWeather] = useState<(typeof WEATHER)[number]["id"]>("dry");
  const [band, setBand] = useState<(typeof RIVAL_BANDS)[number]>("test");
  const [seed, setSeed] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const offered = (circuits.data ?? []).filter((circuit) => circuit.coverage.ribbon);
  const chosen = slug ?? offered[0]?.id ?? null;
  const detail = useCircuit(chosen);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen === null || submitting) return;
    const trimmed = seed.trim();
    if (trimmed !== "" && !/^\d+$/.test(trimmed)) {
      setError("seed must be a whole number, or blank");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: SimulationCreate = {
        circuit_id: chosen,
        grid_position: grid,
        ...(trimmed !== "" ? { seed: Number(trimmed) } : {}),
        // omit defaults so the request body stays byte-identical to the other pickers'
        // and the E-15 cache key namespace does not fork on equivalent requests
        ...(era !== "2026" ? { era } : {}),
        ...(weather !== "dry" ? { weather_profile: weather } : {}),
        ...(band !== "test" ? { rival_band: band } : {}),
      };
      const accepted = await apiPost<JobAccepted>("/v1/simulations", body);
      onRun(accepted.run_id);
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : String(thrown));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-senna-line"
    >
      <div className="flex items-center gap-2 border-b border-senna-line bg-senna-raised px-3 py-2">
        <span aria-hidden className="h-3 w-[3px] shrink-0 bg-senna-accent" />
        <h2 className="text-micro uppercase text-senna-muted">race configuration</h2>
      </div>

      <Section title="circuit">
        <ul className="max-h-56 space-y-px overflow-y-auto">
          {offered.map((circuit) => (
            <li key={circuit.id}>
              <button
                type="button"
                onClick={() => {
                  picked.current = true;
                  setSlug(circuit.id);
                }}
                className={`flex w-full items-baseline justify-between px-2 py-1 text-left text-label ${
                  circuit.id === chosen
                    ? "bg-senna-raised text-senna-accent"
                    : "text-senna-faint hover:text-senna-muted"
                }`}
              >
                <span className="truncate">{circuit.id.replace(/_grand_prix$/, "").replace(/_/g, " ")}</span>
                <span className="ml-2 shrink-0 text-senna-ghost">{circuit.race_laps}L</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="parameters">
        <dl className="grid grid-cols-2 gap-y-2 text-label">
          <div>
            <dt className="text-micro uppercase text-senna-ghost">laps</dt>
            <dd className="text-senna-text">{detail.data?.race_laps ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-micro uppercase text-senna-ghost">length</dt>
            <dd className="text-senna-text">
              {detail.data?.lap_length_m == null
                ? "—"
                : `${(detail.data.lap_length_m / 1000).toFixed(3)} km`}
            </dd>
          </div>
          <div>
            <dt className="text-micro uppercase text-senna-ghost">x-mode</dt>
            <dd className="text-senna-text">{detail.data?.xmode_sections?.length ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-micro uppercase text-senna-ghost">harvest</dt>
            <dd className="text-senna-text">
              {detail.data === undefined ? "—" : `${detail.data.h_max_mj} MJ`}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="conditions">
        <div className="flex flex-wrap gap-1.5">
          {WEATHER.map((option) => (
            <Choice
              key={option.id}
              active={weather === option.id}
              onClick={() => setWeather(option.id)}
            >
              {option.id.replace("_", " ")}
            </Choice>
          ))}
        </div>
        <p className="mt-1.5 text-micro text-senna-ghost">
          {WEATHER.find((option) => option.id === weather)?.blurb}
        </p>
      </Section>

      <Section title="era and rivals">
        <div className="flex flex-wrap gap-1.5">
          {ERAS.map((option) => (
            <Choice key={option} active={era === option} onClick={() => setEra(option)}>
              {option}
            </Choice>
          ))}
          {RIVAL_BANDS.map((option) => (
            <Choice key={option} active={band === option} onClick={() => setBand(option)}>
              {option}
            </Choice>
          ))}
        </div>
        <p className="mt-1.5 text-micro text-senna-ghost">
          test is the held-out rival band — the honest demo setting
        </p>
      </Section>

      <Section title="starting position">
        <div className="flex items-baseline gap-2">
          <span data-testid="grid-readout" className="text-2xl text-senna-accent">
            P{grid}
          </span>
          <span className="text-micro uppercase text-senna-ghost">
            {grid <= 10 ? "top ten" : "outside the top ten"}
          </span>
        </div>
        <label className="mt-2 block">
          <span className="sr-only">grid position</span>
          <input
            type="range"
            min={1} // sourced — SimulationCreate bounds, 5.9.2 (ge=1, le=22)
            max={GRID_SLOTS}
            value={grid}
            onChange={(event) => setGrid(Number(event.target.value))}
            className="w-full accent-senna-accent"
          />
        </label>
        <div className="flex justify-between text-micro text-senna-ghost">
          <span>P1</span>
          <span>P{GRID_SLOTS}</span>
        </div>
      </Section>

      <Section title="seed">
        <input
          type="text"
          inputMode="numeric"
          value={seed}
          onChange={(event) => setSeed(event.target.value)}
          placeholder="blank draws one, echoed back"
          className="w-full rounded-panel border border-senna-line bg-senna-ground px-2 py-1 text-label text-senna-muted placeholder:text-senna-ghost"
        />
      </Section>

      {error !== null && <p className="px-3 pb-2 text-label text-senna-danger">{error}</p>}

      <div className="mt-auto border-t border-senna-line p-3">
        <button
          type="submit"
          disabled={chosen === null || submitting}
          className="w-full rounded-panel border border-senna-accent py-2 text-label uppercase tracking-[0.12em] text-senna-accent hover:bg-senna-accent/10 disabled:opacity-40"
        >
          {submitting ? "queueing" : "run race"}
        </button>
      </div>
    </form>
  );
}
