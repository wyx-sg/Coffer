// frontend/src/components/LegacyScopeRedirect.tsx
//
// Redirect a legacy `/knowledge-bases/:name` deep link to the merged
// `/knowledge/:scope` detail page. `knowledge_base` was its own resource kind
// with its own surface before it became part of the one Knowledge kind; the
// resource name is unchanged by the merge, so it carries straight over as the
// scope segment. Lives in its own file so router.tsx stays component-free.
// (`memory` used to redirect here too, before spec memory split it back out
// into its own kind with its own real surface at /memory.)
import { Navigate, useParams } from "react-router-dom";

export function LegacyScopeRedirect() {
  const name = useParams<{ name: string }>().name ?? "";
  return <Navigate to={`/knowledge/${name}`} replace />;
}
