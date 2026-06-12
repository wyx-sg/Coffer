// frontend/src/components/agents/BuiltinAgentCard.tsx
// Pinned, non-deletable card for Coffer's built-in chat agent ("Coffer
// Assistant"). It is not a registry agent (no config_dir / skills / MCP), so it
// lives ABOVE the detected-agents table rather than inside it.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  /** Display name of the built-in assistant (from GET /chat/agents). */
  name: string;
}

export function BuiltinAgentCard({ name }: Props) {
  const { t } = useTranslation();
  return (
    <Card className="border-primary/20 bg-gradient-to-br from-card to-accent/40">
      <CardContent className="flex flex-wrap items-center justify-between gap-4 py-5">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Sparkles className="size-4" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-foreground">{name}</span>
              <span className="rounded-sm bg-primary/10 px-1.5 py-0.5 text-xs text-primary">
                {t("agents.builtin.badge")}
              </span>
            </div>
            <p className="max-w-prose text-sm text-muted-foreground">
              {t("agents.builtin.description")}
            </p>
          </div>
        </div>
        <Button asChild>
          <Link to="/chat">{t("agents.builtin.startChat")}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
