// frontend/src/pages/ResourceDetailPage.tsx
//
// The /mcp-servers/:name detail route. The MCP servers surface only ever lists
// one kind, so the kind is fixed here rather than read off the URL; the kind
// registry still supplies the page, so a kind module stays the one place that
// says how its detail renders.
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/EmptyState";
import { getKindUI } from "@/lib/components/kindRegistry";

const KIND = "mcp_server";

export function ResourceDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const kindUI = getKindUI(KIND);

  if (kindUI === undefined) {
    return (
      <EmptyState
        title={t("resourceDetail.unknownKind")}
        description={t("resourceDetail.unknownKindBody", { kind: KIND })}
      />
    );
  }

  if (kindUI.DetailPage === undefined) {
    return <Navigate to="/mcp-servers" replace />;
  }

  const DetailPage = kindUI.DetailPage;
  return <DetailPage name={name} />;
}
