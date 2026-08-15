// The strip every section puts its run metadata in. Five copies of this classString
// existed before F23, one of them subtly different for no recorded reason.

import type { ReactNode } from "react";

export default function ViewHeader({ children }: { children: ReactNode }) {
  return (
    <header className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-senna-line bg-senna-surface px-4 py-2 text-label text-senna-faint">
      {children}
    </header>
  );
}
