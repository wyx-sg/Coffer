// frontend/src/components/agents/BuiltinAgentsSection.tsx — spec 008 US8.
// The "Built-in agents" section on the Agents page: Coffer's own LLM agent(s)
// (kind `builtin_agent`) shown alongside the managed external agents, with
// view / create / edit / delete. Self-contained — owns its own list query and
// the create-dialog state; the table owns edit/delete.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Sparkles } from "lucide-react";

import { BuiltinAgentForm } from "@/components/agents/BuiltinAgentForm";
import { BuiltinAgentTable } from "@/components/agents/BuiltinAgentTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useBuiltinAgents } from "@/lib/hooks/useBuiltinAgents";

export function BuiltinAgentsSection() {
  const { t } = useTranslation();
  const { data: agents, isPending, error } = useBuiltinAgents();
  const [showAdd, setShowAdd] = useState(false);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-5 text-primary" />
          <div>
            <h2 className="text-lg font-semibold">{t("builtinAgents.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("builtinAgents.subtitle")}</p>
          </div>
        </div>
        <Button variant="outline" onClick={() => setShowAdd(true)}>
          <Plus className="mr-1 size-4" /> {t("builtinAgents.add")}
        </Button>
      </div>

      {isPending ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-destructive">
            {translateApiError(t, error)}
          </CardContent>
        </Card>
      ) : (agents ?? []).length === 0 ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            {t("builtinAgents.empty")}
          </CardContent>
        </Card>
      ) : (
        <BuiltinAgentTable agents={agents ?? []} />
      )}

      {showAdd ? (
        <BuiltinAgentForm
          agent={null}
          onClose={() => setShowAdd(false)}
          onSaved={() => setShowAdd(false)}
        />
      ) : null}
    </section>
  );
}
