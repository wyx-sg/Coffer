// frontend/src/kinds/channel/ChannelWelcomePanel.tsx
// First-run welcome card shown on /channels when none exist yet — mirrors
// KnowledgeBaseWelcomePanel. Explains the surface and offers the single next
// step (Add channel, which opens the add dialog).
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ChannelWelcomePanel({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("channels.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("channels.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAdd}>{t("channels.add")}</Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("channels.welcome.featureChat.title")}
            body={t("channels.welcome.featureChat.body")}
          />
          <WelcomeFeature
            title={t("channels.welcome.featurePair.title")}
            body={t("channels.welcome.featurePair.body")}
          />
          <WelcomeFeature
            title={t("channels.welcome.featureNotify.title")}
            body={t("channels.welcome.featureNotify.body")}
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
