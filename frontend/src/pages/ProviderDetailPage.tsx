// src/pages/ProviderDetailPage.tsx — one model provider, at /model-providers/<uid>.
//
// Addressed by uid (a provider can be renamed). It renders the same split as
// the list page, with this provider open: header (Test, Edit, ⋯), then one
// column — Used by, Endpoint, Models. The detail has no tabs.
import { useParams } from "react-router-dom";

import { ProvidersSplit } from "@/components/providers/ProvidersSplit";

export function ProviderDetailPage() {
  const { uid = "" } = useParams<{ uid: string }>();
  return <ProvidersSplit uid={uid} />;
}
