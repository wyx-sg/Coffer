// frontend/src/pages/ResourceDetailPage.tsx
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getKindUI } from "@/lib/components/kindRegistry";

export function ResourceDetailPage() {
  const { t } = useTranslation();
  const { kind = "", name = "" } = useParams<{ kind: string; name: string }>();
  const kindUI = getKindUI(kind);

  if (kindUI === undefined) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("resourceDetail.unknownKind")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p>{t("resourceDetail.unknownKindBody", { kind })}</p>
        </CardContent>
      </Card>
    );
  }

  if (kindUI.DetailPage === undefined) {
    return <Navigate to="/mcp-servers" replace />;
  }

  const DetailPage = kindUI.DetailPage;
  return <DetailPage name={name} />;
}
