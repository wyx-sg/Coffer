// frontend/src/pages/KindResourcePage.tsx
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
 * Kind-scoped resource landing page. The 002-ui-shell sidebar gives each
 * resource kind its own nav entry; this renders the list + add CTA for a
 * single kind, reusing that kind's registered Card via ResourceListView.
 * Knowledge bases and memory stores both render through this component.
 */
export function KindResourcePage({ kind, icon: Icon, i18nKey }: KindResourcePageProps) {
  const { t } = useTranslation();
  const addPath = getKindUI(kind)?.addPath;
  const { data: resources, isPending, error } = useResources(kind);
  const hasResources = (resources?.length ?? 0) > 0;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="flex items-center gap-3 text-3xl tracking-tight">
            <Icon className="size-7 text-primary" strokeWidth={1.5} aria-hidden />
            {t(`${i18nKey}.title`)}
          </h1>
          <p className="max-w-prose text-sm text-muted-foreground">{t(`${i18nKey}.subtitle`)}</p>
        </div>
        {hasResources && addPath ? (
          <Button asChild>
            <Link to={addPath}>
              <Plus className="mr-1 size-4" /> {t(`${i18nKey}.add`)}
            </Link>
          </Button>
        ) : null}
      </header>

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
        <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
          <CardContent className="space-y-5 py-10">
            <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
              {t(`${i18nKey}.empty`)}
            </p>
            {addPath ? (
              <Button asChild>
                <Link to={addPath}>
                  <Plus className="mr-1 size-4" /> {t(`${i18nKey}.add`)}
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
