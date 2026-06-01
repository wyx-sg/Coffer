// frontend/src/pages/AgentsPage.tsx — spec 004-agent-registry surface.
// One unified agents table: external agents (kind `agent`) and Coffer's own
// built-in LLM agents (kind `builtin_agent`) are rows in the same DataTable.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, ChevronDown, Plus } from "lucide-react";

import { AgentAddDialog } from "@/components/agents/AgentAddDialog";
import { AgentTable } from "@/components/agents/AgentTable";
import { AgentWelcomePanel } from "@/components/agents/AgentWelcomePanel";
import { BuiltinAgentForm } from "@/components/agents/BuiltinAgentForm";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBuiltinAgents } from "@/lib/hooks/useBuiltinAgents";

export function AgentsPage() {
  const { t } = useTranslation();
  const { data: agents, isPending, error, refetch } = useAgents();
  const builtin = useBuiltinAgents();
  const [showAddExternal, setShowAddExternal] = useState(false);
  const [showAddBuiltin, setShowAddBuiltin] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // Either kind being present means we show the table (and the header add menu)
  // rather than the empty-state welcome panel.
  const hasRows = (agents ?? []).length > 0 || (builtin.data ?? []).length > 0;

  // A small dropdown: "Add agent" registers an external agent; "Add built-in
  // agent" opens the built-in create form. Keeps a single add control above the
  // single table.
  const addMenu = (
    <Popover open={menuOpen} onOpenChange={setMenuOpen}>
      <PopoverTrigger asChild>
        <Button>
          <Plus className="mr-1 size-4" /> {t("agents.add")}
          <ChevronDown className="ml-1 size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-1">
        <button
          type="button"
          className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted"
          onClick={() => {
            setMenuOpen(false);
            setShowAddExternal(true);
          }}
        >
          {t("agents.add")}
        </button>
        <button
          type="button"
          className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted"
          onClick={() => {
            setMenuOpen(false);
            setShowAddBuiltin(true);
          }}
        >
          {t("builtinAgents.add")}
        </button>
      </PopoverContent>
    </Popover>
  );

  return (
    <div className="space-y-6">
      {/* Header action only once rows exist — the empty state's welcome
          panel carries the add call-to-action instead (no dup). */}
      <PageHeader
        icon={Bot}
        title={t("agents.title")}
        subtitle={t("agents.subtitle")}
        actions={hasRows ? addMenu : null}
      />

      {/* The combined external-agent Add dialog — auto-detects installed agents
          and also offers manual registration behind a disclosure. */}
      <AgentAddDialog
        open={showAddExternal}
        onOpenChange={setShowAddExternal}
        onCreated={() => void refetch()}
      />

      {/* The built-in agent create form. */}
      {showAddBuiltin ? (
        <BuiltinAgentForm
          agent={null}
          onClose={() => setShowAddBuiltin(false)}
          onSaved={() => setShowAddBuiltin(false)}
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
      ) : !hasRows ? (
        <AgentWelcomePanel onAddAgent={() => setShowAddExternal(true)} />
      ) : (
        <AgentTable agents={agents ?? []} builtinAgents={builtin.data ?? []} />
      )}
    </div>
  );
}
