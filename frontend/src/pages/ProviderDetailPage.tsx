// src/pages/ProviderDetailPage.tsx — one model provider, at /model-providers/<uid>[/models].
//
// Addressed by uid (a provider can be renamed); the open tab is the path
// segment (useDetailTab). It renders the same split as the list page, with this
// provider open: header (reach, Test, Edit, ⋯), Overview (Used by, Endpoint,
// Models) and Models (which of the endpoint's models it offers).
import { useParams } from "react-router-dom";

import { ProvidersSplit } from "@/components/providers/ProvidersSplit";

export function ProviderDetailPage() {
  const { uid = "" } = useParams<{ uid: string }>();
  return <ProvidersSplit uid={uid} />;
}
