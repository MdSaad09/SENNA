// The 5.13 storyboard moves between sections in single clicks: live -> counterfactual at
// 0:45, counterfactual -> energy at 1:15. Under F23's three tabs those targets sit one
// rail deeper than the tab row, so the beats would cost two clicks each. These inline
// links put the click back where the script needs it, carrying the query the way the nav
// does — and they read better than hunting the rail, because they appear next to the
// thing that prompts the question.

import { Link, useLocation } from "react-router-dom";

interface JumpLinkProps {
  to: string;
  children: string;
}

export default function JumpLink({ to, children }: JumpLinkProps) {
  const { search } = useLocation();
  return (
    <Link
      to={{ pathname: to, search }}
      className="inline-flex items-center gap-1 text-label text-senna-accent hover:underline"
    >
      {children}
      <span aria-hidden>&rarr;</span>
    </Link>
  );
}
