// View 1: the annotated circuit. The picker is the whole configs/circuits.yaml
// library with honest coverage states (F-08) — a circuit without a built ribbon
// says so instead of pretending (plan divergence 5).

import { OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useState } from "react";

import { useCircuit, useCircuits } from "../../api/queries";
import type { CircuitDetail } from "../../api/types";
import CanvasHost from "../../components/CanvasHost";
import CircuitRibbon, { useRibbon } from "./CircuitRibbon";
import Legend from "./Legend";

function RibbonScene({ detail, gltfUrl }: { detail: CircuitDetail; gltfUrl: string }) {
  const ribbon = useRibbon(gltfUrl);
  const [cx, cy, cz] = ribbon.centre;
  return (
    <group position={[-cx, -cy, -cz]}>
      <CircuitRibbon detail={detail} ribbon={ribbon} />
    </group>
  );
}

export default function CircuitExplorerView() {
  const circuits = useCircuits();
  const [slug, setSlug] = useState<string | null>(null);
  const detail = useCircuit(slug);

  useEffect(() => {
    if (slug === null && circuits.data !== undefined) {
      const firstBuilt = circuits.data.find((circuit) => circuit.coverage.ribbon);
      if (firstBuilt !== undefined) setSlug(firstBuilt.id);
    }
  }, [slug, circuits.data]);

  return (
    <div className="flex h-full">
      <aside className="w-56 shrink-0 overflow-y-auto border-r border-neutral-800 p-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          circuit library
        </h2>
        <ul className="mt-2 space-y-1">
          {(circuits.data ?? []).map((circuit) => (
            <li key={circuit.id}>
              <button
                type="button"
                onClick={() => setSlug(circuit.id)}
                className={`w-full rounded px-2 py-1 text-left text-sm ${
                  circuit.id === slug
                    ? "bg-neutral-800 text-neutral-100"
                    : "text-neutral-400 hover:bg-neutral-900"
                }`}
              >
                {circuit.id.replace(/_/g, " ")}
                {!circuit.coverage.ribbon && (
                  <span className="ml-1 text-xs text-neutral-600">(no ribbon yet)</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="relative min-w-0 flex-1">
        <CanvasHost>
          {detail.data?.gltf_url != null && (
            <Suspense fallback={null}>
              <RibbonScene detail={detail.data} gltfUrl={detail.data.gltf_url} />
            </Suspense>
          )}
          <OrbitControls makeDefault />
        </CanvasHost>

        {detail.data !== undefined && detail.data.gltf_url === null && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="text-center text-sm text-neutral-400">
              <p>ribbon not built for this circuit yet</p>
              <p className="mt-1 text-xs text-neutral-600">
                coverage: ribbon {String(detail.data.coverage.ribbon)}, degradation fit{" "}
                {String(detail.data.coverage.deg_fit)} — run make circuits after ingesting
                the event
              </p>
            </div>
          </div>
        )}

        {detail.data !== undefined && detail.data.gltf_url !== null && (
          <div className="absolute bottom-3 left-3 max-w-sm">
            <Legend detail={detail.data} />
          </div>
        )}
      </section>
    </div>
  );
}
