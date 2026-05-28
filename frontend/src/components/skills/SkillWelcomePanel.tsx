// frontend/src/components/skills/SkillWelcomePanel.tsx
// First-run welcome card shown on /skills when no skill is managed yet —
// mirrors AgentWelcomePanel. Explains the surface and offers the single next
// step (Add skill — local-folder import + Git fetch live in that dialog).
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function SkillWelcomePanel({ onAddSkill }: { onAddSkill: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">{t("skills.welcome.title")}</h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("skills.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAddSkill}>{t("skills.add")}</Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("skills.welcome.featureImport.title")}
            body={t("skills.welcome.featureImport.body")}
          />
          <WelcomeFeature
            title={t("skills.welcome.featureDeliver.title")}
            body={t("skills.welcome.featureDeliver.body")}
          />
          <WelcomeFeature
            title={t("skills.welcome.featureDrift.title")}
            body={t("skills.welcome.featureDrift.body")}
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
