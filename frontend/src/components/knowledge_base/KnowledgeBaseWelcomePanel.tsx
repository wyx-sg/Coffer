// frontend/src/components/knowledge_base/KnowledgeBaseWelcomePanel.tsx
// First-run welcome card shown on /knowledge-bases when none exist yet —
// mirrors SkillWelcomePanel. Explains the surface and offers the single next
// step (New knowledge base, which opens the add dialog).
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function KnowledgeBaseWelcomePanel({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="space-y-6 py-10">
        <div className="space-y-2">
          <h2 className="font-serif text-2xl tracking-tight">
            {t("knowledgeBases.welcome.title")}
          </h2>
          <p className="max-w-prose text-sm leading-relaxed text-foreground/80">
            {t("knowledgeBases.welcome.body")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onAdd}>{t("knowledgeBases.add")}</Button>
        </div>
        <ul className="grid gap-3 pt-2 text-sm text-foreground/70 sm:grid-cols-3">
          <WelcomeFeature
            title={t("knowledgeBases.welcome.featureKeyword.title")}
            body={t("knowledgeBases.welcome.featureKeyword.body")}
          />
          <WelcomeFeature
            title={t("knowledgeBases.welcome.featureSemantic.title")}
            body={t("knowledgeBases.welcome.featureSemantic.body")}
          />
          <WelcomeFeature
            title={t("knowledgeBases.welcome.featureAgent.title")}
            body={t("knowledgeBases.welcome.featureAgent.body")}
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
