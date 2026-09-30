// frontend/src/components/mcp/add/ImportFromAgents.tsx — the Add server
// dialog's "Import from your agents" view (board Mcp-ImportAgents; spec
// agent-registry "Adopt a direct MCP entry into Coffer").
//
// Lists each agent's direct MCP entries — the ones in its own config files
// that bypass Coffer — grouped by agent, each with a tick. Import adopts the
// ticked ones one after another through the agent's adopt route: Coffer
// registers the server (secret values move to the keychain first), then takes
// the entry out of the agent's file. An entry that duplicates a server Coffer
// already has is listed but not offered — the adopt route would only refuse it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { entryCommand } from "@/components/agents/mcp/mcpRows";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DialogFooter } from "@/components/ui/dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import {
  useAdoptAgentEntries,
  useAgentDirectMcpEntries,
  type AdoptChoice,
  type AdoptReport,
} from "@/lib/hooks/useAgentDirectMcpEntries";
import { isValidServerName, normaliseServerName } from "@/lib/mcp/pasteParse";

interface Props {
  onBack: () => void;
  /** Called after an import in which every chosen entry was adopted. */
  onDone: (report: AdoptReport) => void;
}

const keyOf = (c: AdoptChoice) => `${c.agent.uid}:${c.entry.source}:${c.entry.name}`;

export function ImportFromAgents({ onBack, onDone }: Props) {
  const { t } = useTranslation();
  const { groups, isLoading } = useAgentDirectMcpEntries();
  const adopt = useAdoptAgentEntries();
  const [unticked, setUnticked] = useState<Set<string>>(new Set());
  const [report, setReport] = useState<AdoptReport | null>(null);

  const offered: AdoptChoice[] = groups.flatMap((g) =>
    g.entries
      .filter((entry) => isValidServerName(normaliseServerName(entry.name)))
      .map((entry) => ({ agent: g.agent, entry })),
  );
  const chosen = offered.filter((c) => !unticked.has(keyOf(c)));
  const toggle = (c: AdoptChoice, on: boolean) =>
    setUnticked((prev) => {
      const next = new Set(prev);
      if (on) next.delete(keyOf(c));
      else next.add(keyOf(c));
      return next;
    });

  const run = () =>
    adopt.mutate(chosen, {
      onSuccess: (r) => {
        if (r.failed.length === 0) onDone(r);
        else setReport(r);
      },
    });

  const byAgent = groups
    .map((g) => ({ g, picked: chosen.filter((c) => c.agent.uid === g.agent.uid) }))
    .filter(({ picked }) => picked.length > 0);
  const empty = !isLoading && groups.every((g) => g.entries.length + g.duplicates.length === 0);

  return (
    <>
      <div className="max-h-[50vh] space-y-3 overflow-y-auto pr-1">
        {empty ? <p className="text-sm text-text-muted">{t("mcp.import.none")}</p> : null}
        {groups
          .filter((g) => g.entries.length + g.duplicates.length > 0)
          .map((g) => (
            <section key={g.agent.uid} className="space-y-1.5">
              <h3 className="text-xs font-label text-text-muted">
                {agentTypeLabel(g.agent.type ?? g.agent.name)}
              </h3>
              {g.entries.map((entry) => {
                const c = { agent: g.agent, entry };
                const valid = isValidServerName(normaliseServerName(entry.name));
                return (
                  <label
                    key={keyOf(c)}
                    className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border p-2.5"
                  >
                    <Checkbox
                      className="mt-0.5"
                      checked={valid && !unticked.has(keyOf(c))}
                      disabled={!valid || adopt.isPending}
                      aria-label={t("mcp.add.include", { name: entry.name })}
                      onChange={(e) => toggle(c, e.target.checked)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-sm text-text">{entry.name}</span>
                      <span className="block truncate font-mono text-xs text-text-muted">
                        {entryCommand(entry)}
                      </span>
                      {!valid ? (
                        <span className="block text-xs text-danger">
                          {t("mcp.import.nameUnusable")}
                        </span>
                      ) : null}
                    </span>
                  </label>
                );
              })}
              {g.duplicates.map((entry) => (
                <div
                  key={`dup:${entry.source}:${entry.name}`}
                  className="rounded-lg border border-border-subtle p-2.5 opacity-disabled"
                >
                  <span className="block font-mono text-sm text-text">{entry.name}</span>
                  <span className="block text-xs text-text-muted">
                    {t("mcp.import.alreadyInCoffer", { name: entry.matches_resource })}
                  </span>
                </div>
              ))}
            </section>
          ))}
      </div>

      {chosen.length > 0 ? (
        <div className="space-y-1 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs text-text-muted">
          <p className="font-label text-text">{t("mcp.import.whatHappens")}</p>
          <p>
            {t("mcp.import.happensCoffer", { names: chosen.map((c) => c.entry.name).join(", ") })}
          </p>
          {byAgent.map(({ g, picked }) => (
            <p key={g.agent.uid}>
              {t("mcp.import.happensAgent", {
                agent: agentTypeLabel(g.agent.type ?? g.agent.name),
                names: picked.map((c) => c.entry.name).join(", "),
              })}
            </p>
          ))}
          <p>{t("mcp.import.keepNote")}</p>
        </div>
      ) : null}

      {report ? (
        <Alert variant="error">
          <AlertDescription>
            {t("mcp.import.partial", {
              done: report.adopted.length,
              total: report.adopted.length + report.failed.length,
            })}
            <ul className="mt-1 list-inside list-disc">
              {report.failed.map((f) => (
                <li key={f.name}>
                  {t("mcp.import.entryFailed", { name: f.name, reason: f.message })}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <DialogFooter>
        <Button variant="ghost" className="sm:mr-auto" onClick={onBack} disabled={adopt.isPending}>
          {t("mcp.add.back")}
        </Button>
        <Button disabled={adopt.isPending || chosen.length === 0} onClick={run}>
          {adopt.isPending
            ? t("mcp.import.importing")
            : t("mcp.import.importN", { count: chosen.length })}
        </Button>
      </DialogFooter>
    </>
  );
}
