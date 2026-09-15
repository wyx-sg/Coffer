// src/pages/KindResourcePage.tsx — kind-scoped resource landing page (list + add CTA).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { getKindUI } from "@/lib/components/kindRegistry";
import { ResourceListView } from "@/lib/components/ResourceListView";
import { useResources } from "@/lib/hooks/useResources";
import { translateApiError } from "@/lib/api/errors";

interface KindResourcePageProps {
  /** Backend kind name, e.g. "knowledge_base" — must be in the kindRegistry. */
  kind: string;
  /** Header icon, matching the kind's sidebar entry. */
  icon: LucideIcon;
  /**
   * i18n namespace for this page, e.g. "knowledgeBases". Pulls
   * `<ns>.title`, `<ns>.subtitle`, `<ns>.add`, `<ns>.empty`.
   */
  i18nKey: string;
}

/**
 * Kind-scoped resource landing page. The ui-shell sidebar gives each
 * resource kind its own nav entry; this renders the list + add CTA for a
 * single kind, reusing that kind's registered Card via ResourceListView.
 * Knowledge bases and memory stores both render through this component.
 */
export function KindResourcePage({ kind, icon, i18nKey }: KindResourcePageProps) {
  const { t } = useTranslation();
  const addPath = getKindUI(kind)?.addPath;
  const { data: resources, isPending, error } = useResources(kind);
  const hasResources = (resources?.length ?? 0) > 0;

  const addButton = addPath ? (
    <Button asChild>
      <Link to={addPath}>
        <Plus className="mr-1 size-4" /> {t(`${i18nKey}.add`)}
      </Link>
    </Button>
  ) : null;

  return (
    <div className="space-y-8">
      <PageHeader
        icon={icon}
        title={t(`${i18nKey}.title`)}
        subtitle={t(`${i18nKey}.subtitle`)}
        actions={hasResources ? addButton : null}
      />

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
        <ResourceListView resources={resources ?? []} />
      ) : (
        <EmptyState icon={icon} title={t(`${i18nKey}.empty`)} action={addButton} />
      )}
    </div>
  );
}
