// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page, in two sections that mirror the Skills
// and MCP-servers tabs (Coffer-managed vs the agent's own):
//
//   A. Coffer-managed memory — Coffer keeps its own memory format and agents
//      reach it ONLY via the MCP gateway. The stores are managed on the
//      standalone Memory page, so this tab does not re-list them: the shared
//      ManagedLinkCard points straight there.
//   B. The agent's own memory — the coding agent's OWN native per-project memory
//      stores (e.g. Claude Code's ~/.claude/projects/<project>/memory/), shown
//      read-only as a table of (project, path, item count) with open / reveal
//      (FileActions). This is NOT Coffer memory and NOT the CLAUDE.md instructions
//      file; it is the agent's native memory, surfaced for reference (and, later,
//      import into Coffer).
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { CofferGatewayRow } from "@/components/agents/AgentManagedLink";
import { AgentHookToggle } from "@/components/agents/AgentHookControls";
import { AgentNativeMemoryBulkActions } from "@/components/agents/AgentMemoryBulkActions";
import { DataTable, type Column } from "@/components/DataTable";
import { RowActions } from "@/components/RowActions";
import { useFileActionItems } from "@/lib/fileActionItems";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut, NativeMemoryStore } from "@/lib/api/agents";
import { useAgentNativeMemory, useImportNativeMemory, usePatchAgent } from "@/lib/hooks/useAgents";

/** Toggle ROW (no Card — the parent's combined box provides it) that disables
 * the agent's OWN native memory (writes/restores the agent's config) so it uses
 * Coffer as the shared store. Reads `agent.disable_native_memory`; flips it via
 * PATCH /agents/{name}. */
function DisableNativeMemoryRow({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const patch = usePatchAgent();
  const disabled = agent.disable_native_memory ?? false;

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-1">
        <Label htmlFor="disable-native-memory" className="text-sm font-medium">
          {t("agents.memoryTab.disableNativeLabel")}
        </Label>
        <p className="max-w-prose text-xs text-muted-foreground">
          {t("agents.memoryTab.disableNativeHelp")}
        </p>
      </div>
      <Switch
        id="disable-native-memory"
        checked={disabled}
        disabled={patch.isPending}
        onCheckedChange={(next) =>
          patch.mutate(
            { name: agent.name, body: { disable_native_memory: next } },
            {
              onSuccess: () =>
                toast.success(
                  next
                    ? t("agents.memoryTab.disableNativeOn")
                    : t("agents.memoryTab.disableNativeOff"),
                ),
              onError: (e) => toast.error(translateApiError(t, e)),
            },
          )
        }
      />
    </div>
  );
}

/** Per-row "import this native memory store into Coffer" button: bulk-remembers
 * the store's items into the matching Coffer project store, then organizes. */
function ImportButton({ agentName, store }: { agentName: string; store: NativeMemoryStore }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const importMut = useImportNativeMemory(agentName);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={importMut.isPending}
      onClick={() =>
        importMut.mutate(
          { memoryDir: store.memory_dir, projectPath: store.path },
          {
            onSuccess: (r) =>
              r.store
                ? toast.success(
                    t("agents.memoryTab.importDone", {
                      count: r.imported,
                      project: store.project,
                    }),
                  )
                : toast.error(t("agents.memoryTab.importNoProject", { project: store.project })),
            onError: (e) => toast.error(translateApiError(t, e)),
          },
        )
      }
    >
      {importMut.isPending ? t("agents.memoryTab.importing") : t("agents.memoryTab.import")}
    </Button>
  );
}

/** Row actions: import (primary) + open/reveal folded into the "⋯" menu so the
 * row never sprawls into three wrapping buttons. */
function NativeMemoryRowActions({
  agentName,
  store,
}: {
  agentName: string;
  store: NativeMemoryStore;
}) {
  const { t } = useTranslation();
  const fileItems = useFileActionItems(store.memory_dir);
  return (
    <RowActions
      primary={<ImportButton agentName={agentName} store={store} />}
      items={fileItems}
      menuAriaLabel={t("common.moreActions")}
    />
  );
}

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const native = useAgentNativeMemory(agent.name);

  const columns: Column<NativeMemoryStore>[] = [
    {
      key: "project",
      header: t("agents.memoryTab.colProject"),
      className: "whitespace-nowrap",
      cell: (s) => <span className="text-sm font-medium">{s.project}</span>,
    },
    {
      key: "path",
      header: t("agents.memoryTab.colPath"),
      // Prefer the real project path; for Codex every row shares one memory_dir,
      // so the cwd in `path` is what distinguishes (and is more useful than the
      // internal memory folder for Claude Code too).
      cell: (s) => (
        <span className="line-clamp-1 max-w-md font-mono text-xs text-muted-foreground">
          {s.path ?? s.memory_dir}
        </span>
      ),
    },
    {
      key: "items",
      header: t("agents.memoryTab.colItems"),
      className: "whitespace-nowrap tabular-nums text-right",
      cell: (s) => <span className="text-muted-foreground">{s.item_count}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => <NativeMemoryRowActions agentName={agent.name} store={s} />,
    },
  ];

  return (
    <div className="space-y-3">
      {/* One combined box (like the Skills tab): the "managed by Coffer" pointer
          on top, then the memory toggles below it — disable native memory, and
          the session-start rules-injection hook (same "what Coffer feeds the
          agent at session start" concern). The per-project native stores follow
          in their own card. */}
      <Card className="divide-y p-0">
        <div className="p-4">
          <CofferGatewayRow
            agentName={agent.name}
            title={t("agents.cofferManaged")}
            hint={t("agents.memoryTab.accessViaGateway")}
            buttonLabel={t("agents.memoryTab.openMemoryPage")}
            onOpen={() => navigate("/memory")}
            notInstalledHint={t("agents.memoryTab.notInstalled")}
          />
        </div>
        <div className="p-4">
          <DisableNativeMemoryRow agent={agent} />
        </div>
        <div className="p-4">
          <AgentHookToggle name={agent.name} />
        </div>
      </Card>

      <Card className="space-y-3 p-4">
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">{t("agents.agentOwn")}</h3>
          <p className="text-xs text-muted-foreground">{t("agents.memoryTab.nativeHint")}</p>
        </div>

        {native.isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : native.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, native.error)}</p>
        ) : (
          <DataTable
            rows={native.data?.items ?? []}
            columns={columns}
            // Codex rows share one memory_dir, so key by the routed project too.
            rowKey={(s) => `${s.memory_dir}::${s.path ?? s.project}`}
            search={{
              accessor: (s) => `${s.project} ${s.path ?? ""} ${s.memory_dir}`,
              placeholder: t("agents.memoryTab.searchPlaceholder"),
            }}
            selection={{
              ariaSelectAll: t("common.bulk.selectAll"),
              ariaSelectRow: (s) => `${t("common.bulk.selectRow")}: ${s.project}`,
              bulkLabel: (count) => t("common.bulk.selected", { count }),
              clearLabel: t("common.clear"),
              renderBulkActions: ({ selectedRows, clear }) => (
                <AgentNativeMemoryBulkActions
                  agentName={agent.name}
                  rows={selectedRows}
                  onDone={clear}
                />
              ),
            }}
            emptyMessage={t("agents.memoryTab.nativeEmpty")}
          />
        )}
      </Card>
    </div>
  );
}
