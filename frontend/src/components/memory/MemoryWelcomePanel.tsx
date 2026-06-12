// frontend/src/components/memory/MemoryWelcomePanel.tsx
// First-run card shown on /memory before any store has facts. Memory stores are
// auto-provisioned (a global store + one per project), so there is no "Add"
// action — the panel just explains the surface.
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";

export function MemoryWelcomePanel() {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("memory.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("memory.welcome.body")}
          </p>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("memory.welcome.featureRecall.title")}
            body={t("memory.welcome.featureRecall.body")}
          />
          <WelcomeFeature
            title={t("memory.welcome.featureLocal.title")}
            body={t("memory.welcome.featureLocal.body")}
          />
          <WelcomeFeature
            title={t("memory.welcome.featureAgent.title")}
            body={t("memory.welcome.featureAgent.body")}
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
