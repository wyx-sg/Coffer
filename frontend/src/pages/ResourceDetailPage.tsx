// frontend/src/pages/ResourceDetailPage.tsx
// Detail route for `/mcp-servers/:kind/:name`. Only the `mcp_server` kind has a
// detail page here — knowledge and memory have their own routes — so an
// unknown kind gets a card saying so rather than a blank page.
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { McpServerDetailPage } from "./McpServerDetailPage";

export function ResourceDetailPage() {
  const { t } = useTranslation();
  const { kind = "" } = useParams<{ kind: string; name: string }>();

  if (kind === "mcp_server") {
    return <McpServerDetailPage />;
  }

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
