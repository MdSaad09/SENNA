// Eight near-identical centred overlays existed across the six views: waiting on a
// worker, a failed run, a circuit with no ribbon, a compound with no fit. They all say
// the same two things — what the state is, and what to do about it.

import type { ReactNode } from "react";

interface RunStatusOverlayProps {
  message: ReactNode;
  /** what the reader can do — a make target, a URL shape, a hint. Omitted when nothing helps. */
  hint?: ReactNode;
  failed?: boolean;
}

export default function RunStatusOverlay({ message, hint, failed = false }: RunStatusOverlayProps) {
  return (
    <div className="absolute inset-0 grid place-items-center p-6">
      <div className="max-w-md text-center">
        <p className={`text-label ${failed ? "text-senna-danger" : "text-senna-muted"}`}>
          {message}
        </p>
        {hint !== undefined && <p className="mt-2 text-[11px] text-senna-ghost">{hint}</p>}
      </div>
    </div>
  );
}
