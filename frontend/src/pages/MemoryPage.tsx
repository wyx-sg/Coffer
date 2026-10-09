// frontend/src/pages/MemoryPage.tsx — the Memory page: the sync between the agents' own memories
// (spec memory "Manage memory sync in the web UI and on the command line").
//
// Coffer keeps every memory an agent wrote for itself in a hub in the vault and
// writes each one into the person's other agents, in their own memory format;
// each agent curates and loads its memory itself. The header carries Sync now
// (its ▾ holds the automatic sync's switch and interval), when memory last
// synced and syncs next, and a ⋯ menu with Undo sync…. Below, in order: what
// the last sync could not read or withheld, a first or large sync waiting for
// Write or Cancel, the hub's projects, and this machine's agents with their own
// curation and Curate now. Nothing on the page edits a memory's text: the
// person edits memory in the agent's own memory directory.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Brain, Undo2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { CodexImportSetting } from "@/components/memory/CodexImportSetting";
import { MemoryAgentsTable } from "@/components/memory/MemoryAgentsTable";
import { MemoryPreviewPanel } from "@/components/memory/MemoryPreviewPanel";
import { MemoryProjectsTable } from "@/components/memory/MemoryProjectsTable";
import { MemorySyncButton } from "@/components/memory/MemorySyncButton";
import { MemorySyncClock } from "@/components/memory/MemorySyncClock";
import { MemorySyncProblems } from "@/components/memory/MemorySyncProblems";
import { UndoSyncDialog } from "@/components/memory/UndoSyncDialog";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { translateApiError } from "@/lib/api/errors";
import { useMemorySyncState } from "@/lib/hooks/useMemory";
import { parsePreview, reportFailures, reportWithheld } from "@/lib/memory/syncFacts";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: state, isPending, error, refetch } = useMemorySyncState();
  const [undoing, setUndoing] = useState(false);
  const preview = state ? parsePreview(state.preview) : null;
  const agents = state?.agents ?? [];
  const noAgents = Boolean(state) && agents.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title={t("memory.title")}
        experimental
        subtitle={
          state ? (
            <MemorySyncClock lastSyncedAt={state.last_synced_at} running={state.running} />
          ) : (
            t("memory.subtitle")
          )
        }
        actions={
          state && !noAgents ? (
            <>
              <MemorySyncButton running={state.running} />
              <ActionMenu
                label={t("memory.moreActions")}
                actions={[
                  {
                    key: "undo",
                    label: t("memory.undo.menu"),
                    description: t("memory.undo.menuDescription"),
                    icon: Undo2,
                    destructive: true,
                    onSelect: () => setUndoing(true),
                  },
                ]}
              />
            </>
          ) : null
        }
      />

      {error ? (
        <EmptyState
          icon={Brain}
          tone="error"
          title={t("memory.loadFailed")}
          description={translateApiError(t, error)}
          action={<Button onClick={() => void refetch()}>{t("common.retry")}</Button>}
        />
      ) : noAgents ? (
        <EmptyState
          icon={Brain}
          title={t("memory.noAgents.title")}
          description={t("memory.noAgents.body")}
          action={
            <Button asChild>
              <Link to="/agents">{t("memory.noAgents.open")}</Link>
            </Button>
          }
        />
      ) : (
        <>
          {state ? (
            <MemorySyncProblems
              failures={reportFailures(state.last_report)}
              withheld={reportWithheld(state.last_report)}
            />
          ) : null}
          {state && preview ? (
            <MemoryPreviewPanel preview={preview} projects={state.projects} />
          ) : null}
          <Section as="h2" title={t("memory.projects.title")} testId="memory-projects">
            <p className="text-xs text-text-muted">{t("memory.projects.description")}</p>
            <MemoryProjectsTable
              projects={state?.projects ?? []}
              globalMemories={state?.global_memories ?? 0}
              isLoading={isPending}
            />
          </Section>
          <Section as="h2" title={t("memory.agents.title")} testId="memory-agents">
            <p className="text-xs text-text-muted">{t("memory.agents.description")}</p>
            <MemoryAgentsTable agents={agents} isLoading={isPending} />
            {agents.some((a) => a.agent_type === "codex") ? (
              <CodexImportSetting value={state?.codex_imports_claude ?? null} />
            ) : null}
          </Section>
        </>
      )}

      <UndoSyncDialog open={undoing} onOpenChange={setUndoing} agents={agents} />
    </div>
  );
}
