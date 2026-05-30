// frontend/src/components/agents/AgentWelcomePanel.tsx — spec 004 v2.
// First-run welcome card shown on /agents when no agent is registered yet —
// mirrors the resources WelcomePanel. Explains the surface and offers the
// single next step (Add agent — detection + manual add live in that dialog).
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function AgentWelcomePanel({ onAddAgent }: { onAddAgent: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("agents.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("agents.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAddAgent}>{t("agents.add")}</Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("agents.welcome.featureDetect.title")}
            body={t("agents.welcome.featureDetect.body")}
          />
          <WelcomeFeature
            title={t("agents.welcome.featureConfig.title")}
            body={t("agents.welcome.featureConfig.body")}
          />
          <WelcomeFeature
            title={t("agents.welcome.featureMcp.title")}
            body={t("agents.welcome.featureMcp.body")}
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
