// frontend/src/pages/AgentsPage.tsx — spec 004-agent-registry surface.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentAddForm } from "@/components/agents/AgentAddForm";
import { AgentTable } from "@/components/agents/AgentTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useAgents, useDetectAgents } from "@/lib/hooks/useAgents";

export function AgentsPage() {
  const { t } = useTranslation();
  const { data: agents, isPending, error, refetch } = useAgents();
  const detect = useDetectAgents();
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("agents.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("agents.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              await detect.mutateAsync();
              await refetch();
            }}
            disabled={detect.isPending}
          >
            {detect.isPending ? t("common.loading") : t("agents.detect")}
          </Button>
          <Button onClick={() => setShowAdd(true)}>{t("agents.add")}</Button>
        </div>
      </div>

      {showAdd ? (
        <AgentAddForm
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            void refetch();
            setShowAdd(false);
          }}
        />
      ) : null}

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("agents.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : (agents ?? []).length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("agents.empty")}
          </CardContent>
        </Card>
      ) : (
        <AgentTable agents={agents ?? []} />
      )}
    </div>
  );
}
