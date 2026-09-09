// frontend/src/components/knowledge/KnowledgeWelcomePanel.tsx
// First-run card shown on /knowledge before any scope holds anything. The
// global and per-project scopes auto-provision, so the panel explains the
// surface and offers the one deliberate next step: a named collection.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function KnowledgeWelcomePanel({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("knowledge.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("knowledge.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAdd}>{t("knowledge.add")}</Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("knowledge.welcome.featureEntries.title")}
            body={t("knowledge.welcome.featureEntries.body")}
          />
          <WelcomeFeature
            title={t("knowledge.welcome.featureDocuments.title")}
            body={t("knowledge.welcome.featureDocuments.body")}
          />
          <WelcomeFeature
            title={t("knowledge.welcome.featureLocal.title")}
            body={t("knowledge.welcome.featureLocal.body")}
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
