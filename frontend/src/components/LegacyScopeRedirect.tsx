// frontend/src/components/LegacyScopeRedirect.tsx
//
// Redirect a legacy `/memory/:name` or `/knowledge-bases/:name` deep link to the
// merged `/knowledge/:scope` detail page. `memory` and `knowledge_base` were two
// resource kinds with two surfaces before they became one Knowledge kind; the
// resource name is unchanged by the merge, so it carries straight over as the
// scope segment. Lives in its own file so router.tsx stays component-free.
import { Navigate, useParams } from "react-router-dom";

export function LegacyScopeRedirect() {
  const name = useParams<{ name: string }>().name ?? "";
  return <Navigate to={`/knowledge/${name}`} replace />;
}
