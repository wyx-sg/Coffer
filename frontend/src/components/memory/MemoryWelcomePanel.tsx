// frontend/src/components/memory/MemoryWelcomePanel.tsx
// First-run card shown on /memory before any partition exists — the same
// welcome every other list surface gives (skills, knowledge, agents, channels,
// providers), so arriving at an empty Memory reads like arriving at an empty
// anything else.
//
// The one next step is READ, not Add: nothing here is user-created. Coffer
// distils what the agents already learned out of their own native memories and
// never writes back to them, so the only thing a developer can do on an empty
// Memory is tell it to go and look.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  onRead: () => void;
  reading: boolean;
}

export function MemoryWelcomePanel({ onRead, reading }: Props) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="text-2xl">{t("memory.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("memory.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onRead} disabled={reading}>
            <RefreshCw className={reading ? "mr-1 size-4 animate-spin" : "mr-1 size-4"} />
            {reading ? t("memory.reading") : t("memory.readFromAgents")}
          </Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("memory.welcome.featureRead.title")}
            body={t("memory.welcome.featureRead.body")}
          />
          <WelcomeFeature
            title={t("memory.welcome.featureShape.title")}
            body={t("memory.welcome.featureShape.body")}
          />
          <WelcomeFeature
            title={t("memory.welcome.featureOneWay.title")}
            body={t("memory.welcome.featureOneWay.body")}
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
