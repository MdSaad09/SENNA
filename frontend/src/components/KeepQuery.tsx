// A redirect that keeps the query. `?run=`, `?seed=` and the counterfactual's
// `?year=&round=&driver=` are the whole payload of a demo link (5.13) — dropping them on
// the hop would land the viewer on a configured section with nothing configured.

import { Navigate, useLocation } from "react-router-dom";

export default function KeepQuery({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={{ pathname: to, search }} replace />;
}
