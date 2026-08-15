// The second-level rail. Three tabs cannot hold six views flat — 5.10.3 allows one
// mounted canvas, so sections have to be navigated rather than scrolled past — and this
// is what does the navigating. Links, not buttons: each section is a real URL, and the
// current query rides along so the 5.13 beats stay one click.

import { NavLink } from "react-router-dom";

export interface Section {
  to: string;
  label: string;
}

interface SegmentedProps {
  sections: Section[];
  search: string;
}

export default function Segmented({ sections, search }: SegmentedProps) {
  return (
    <nav className="flex gap-5 border-b border-senna-line bg-senna-ground px-5">
      {sections.map((section) => (
        <NavLink
          key={section.to}
          to={{ pathname: section.to, search }}
          className={({ isActive }) =>
            `-mb-px border-b py-1.5 text-label uppercase ${
              isActive
                ? "border-senna-accent text-senna-accent"
                : "border-transparent text-senna-faint hover:text-senna-muted"
            }`
          }
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
