// frontend/src/pages/ResourcesPage.tsx
import { useTranslation } from "react-i18next";
import { Server } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";
import { AddMcpServerDialog } from "@/kinds/mcp/AddMcpServerDialog";
import { McpServersTable } from "@/kinds/mcp/McpServersTable";
import { WelcomePanel } from "./resources/WelcomePanel";
import { useResources } from "@/lib/hooks/useResources";
import { translateApiError } from "@/lib/api/errors";

/**
 * The MCP servers surface (nav: "MCP servers"; route /mcp-servers). Empty →
 * a welcome card; otherwise the shared DataTable (search / filter / pagination
 * + row multi-select bulk actions), with a row click opening the server's
 * detail page.
 *
 * Scopes the query to `mcp_server` SERVER-SIDE. Filtering client-side off the
 * kind registry was wrong: `memory` and `knowledge_base` register their own
 * UIs too, so a "kind has a registered UI" filter let their stores leak into
 * this list. Asking the backend for one kind is correct no matter what else is
 * registered in the browser.
 */
export function ResourcesPage() {
  const { t } = useTranslation();
  const { data: resources, isPending, error } = useResources("mcp_server");
  const visible = resources ?? [];
  const hasResources = visible.length > 0;

  return (
    <div className="space-y-8">
      <PageHeader
        icon={Server}
        title={t("resources.title")}
        subtitle={t("resources.subtitle")}
        actions={hasResources ? <AddMcpServerDialog /> : null}
      />

      {!hasResources && !isPending && !error ? <WelcomePanel /> : null}

      {isPending ? (
        <Card className="paper-card">
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card className="paper-card border-destructive/40">
          <CardHeader>
            <CardTitle className="font-serif text-destructive">
              {t("resources.loadFailed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : hasResources ? (
        <McpServersTable resources={visible} />
      ) : null}
    </div>
  );
}
