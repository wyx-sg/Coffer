// src/components/shell/redirects.tsx — the legacy redirects the route table needs a component for.
import { Navigate, useLocation, useParams } from "react-router-dom";

/** `/chat/:id` → `/conversations/:id`: Chat was renamed Conversations (spec
 *  web-ui "Keep the sidebar to its fifteen entries"), and an old bookmark to a
 *  conversation keeps opening it. */
export function ChatRedirect() {
  const { id } = useParams<{ id?: string }>();
  const { search, hash } = useLocation();
  const to = id ? `/conversations/${encodeURIComponent(id)}` : "/conversations";
  return <Navigate to={`${to}${search}${hash}`} replace />;
}

/** `/settings` opens the modal on General, keeping the page underneath. */
export function SettingsIndexRedirect() {
  const { state } = useLocation();
  return <Navigate to="/settings/general" replace state={state} />;
}
