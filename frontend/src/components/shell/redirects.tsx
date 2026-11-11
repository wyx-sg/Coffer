// src/components/shell/redirects.tsx — the redirects the route table needs a component for.
import { Navigate, useLocation, useParams } from "react-router-dom";

/** `/settings` opens the modal on General, keeping the page underneath. */
export function SettingsIndexRedirect() {
  const { state } = useLocation();
  return <Navigate to="/settings/general" replace state={state} />;
}

/** The old per-project Memory addresses (`/memory/projects/<folder>`) open the
 *  same scope on the Memory page (`/memory?scope=`); `/memory/global` opens the page. */
export function MemoryScopeRedirect() {
  const { folder } = useParams<{ folder?: string }>();
  return <Navigate to={folder ? `/memory?scope=${encodeURIComponent(folder)}` : "/memory"} replace />;
}
