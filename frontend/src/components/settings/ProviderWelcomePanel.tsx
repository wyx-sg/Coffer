// frontend/src/components/settings/ProviderWelcomePanel.tsx
// First-run welcome card shown on /model-providers when no provider exists yet
// — mirrors pages/resources/WelcomePanel and ChannelWelcomePanel. Explains the
// surface in one paragraph and offers the single next step (Add, which opens
// the same dialog the header button does once providers exist).
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ProviderWelcomePanel({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="text-2xl">{t("settings.connections.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("settings.connections.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAdd}>
            <Plus className="mr-1.5 size-4" aria-hidden />
            {t("settings.connections.add")}
          </Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("settings.connections.welcome.featureShare.title")}
            body={t("settings.connections.welcome.featureShare.body")}
          />
          <WelcomeFeature
            title={t("settings.connections.welcome.featureCurate.title")}
            body={t("settings.connections.welcome.featureCurate.body")}
          />
          <WelcomeFeature
            title={t("settings.connections.welcome.featureEngine.title")}
            body={t("settings.connections.welcome.featureEngine.body")}
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
