// src/components/shell/redirects.tsx — the redirect the route table needs a component for.
import { Navigate, useLocation } from "react-router-dom";

/** `/settings` opens the modal on General, keeping the page underneath. */
export function SettingsIndexRedirect() {
  const { state } = useLocation();
  return <Navigate to="/settings/general" replace state={state} />;
}
