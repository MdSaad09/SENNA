// Two typographic roles that carry meaning, so they get names rather than classStrings.

import type { ReactNode } from "react";

/** The machined uppercase caption above a figure. */
export function MicroLabel({ children }: { children: ReactNode }) {
  return <span className="text-micro uppercase text-senna-faint">{children}</span>;
}

/** A view's statement of what it is not — spec 5.10.2 gives every view one, and
 *  honesty.test.tsx pins all six. Deliberately quiet but never hidden: the credibility
 *  of the whole dashboard rests on these being present and legible. */
export function HonestyNote({ children }: { children: ReactNode }) {
  return <p className="text-label leading-relaxed text-senna-ghost">{children}</p>;
}
