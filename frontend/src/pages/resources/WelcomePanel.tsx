import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { AddMcpServerDialog } from "@/kinds/mcp/AddMcpServerDialog";

/**
 * First-run welcome card — shown on `/resources` when no resource is
 * registered yet. Explains Coffer in one sentence and offers the single
 * obvious next step (spec 002-ui-shell §User Story 1).
 */
export function WelcomePanel() {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("resources.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("resources.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <AddMcpServerDialog />
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("resources.welcome.featureAggregate.title")}
            body={t("resources.welcome.featureAggregate.body")}
          />
          <WelcomeFeature
            title={t("resources.welcome.featureCurate.title")}
            body={t("resources.welcome.featureCurate.body")}
          />
          <WelcomeFeature
            title={t("resources.welcome.featureLocal.title")}
            body={t("resources.welcome.featureLocal.body")}
          />
        </ul>
      </CardContent>
    </Card>
  );
}

function WelcomeFeature({ title, body }: { title: string; body: string }) {
  return (
    <li className="rounded-lg border border-border/60 bg-card/70 p-3 leading-relaxed">
      <div className="mb-1 font-medium text-foreground">{title}</div>
      <div className="text-xs text-muted-foreground">{body}</div>
    </li>
  );
}
