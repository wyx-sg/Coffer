// frontend/src/components/memory/MemoryNeedsYou.tsx
//
// Everything on the Memory page that waits on the person, as one banner over
// the split (spec memory "Preview a first or large sync", "Fail a broken
// reader loudly and in isolation", "Withhold a memory that looks like a
// secret"): a first or large sync waiting for **Write**, each source the last
// sync could not read, each memory it withheld because it looked like a
// secret, and each agent Coffer cannot write into (its own memory is off, a
// layout it does not recognise). The banner counts them in one line; **Review**
// opens a drawer that lists them. The preview is one collapsed line per agent
// and project with its counts (one that removes anything starts open), and
// opens down to each memory; **Write** and **Cancel** are the footer. Problems
// show their file with Reveal; an agent links to its Memory tab.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, CircleAlert } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { SyncAgent } from "@/lib/api/memoryTypes";
import { useCancelPreview, useWritePreview } from "@/lib/hooks/useMemory";
import {
  projectName,
  type PreviewRow,
  type SourceProblem,
  type SyncPreview,
} from "@/lib/memory/syncFacts";

interface Props {
  preview: SyncPreview | null;
  failures: readonly SourceProblem[];
  withheld: readonly SourceProblem[];
  agents: readonly SyncAgent[];
  /** Open one memory (a preview row's title) in the memory drawer. */
  onOpenMemory?: (entry: string, project: string) => void;
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function Problems({ items, reason }: { items: readonly SourceProblem[]; reason: boolean }) {
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {items.map((p) => (
        <li key={`${p.agent}:${p.path}`} className="flex flex-col gap-0.5">
          <span className="inline-flex items-center gap-1.5">
            <AgentBadge type={p.agent} name={agentTypeLabel(p.agent)} size="sm" showName />
          </span>
          <span className="font-mono text-2xs text-text-muted [overflow-wrap:anywhere]">
            {abbreviateHomePath(p.path)}
          </span>
          {reason && p.reason ? <span className="text-xs text-text-muted">{p.reason}</span> : null}
          <FileActions filePath={p.path} className="mt-1" />
        </li>
      ))}
    </ul>
  );
}

function PreviewGroup({
  row,
  onOpenMemory,
}: {
  row: PreviewRow;
  onOpenMemory?: (entry: string, project: string) => void;
}) {
  const { t } = useTranslation();
  const counts = (["write", "update", "remove"] as const)
    .filter((a) => row[a] > 0)
    .map((a) => t(`memory.preview.count.${a}`, { count: row[a] }))
    .join(" · ");
  return (
    <li>
      <details
        open={row.remove > 0}
        className="group rounded-lg border border-border-subtle [&_summary::-webkit-details-marker]:hidden"
      >
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm">
          <ChevronRight
            className="size-3.5 shrink-0 text-text-subtle transition-transform group-open:rotate-90"
            aria-hidden
          />
          <AgentBadge type={row.agent} name={agentTypeLabel(row.agent)} size="sm" showName />
          <span className="text-text-muted" aria-hidden>
            ←
          </span>
          <span className="min-w-0 truncate font-medium" title={row.project || undefined}>
            {row.project ? projectName(row.project) : t("memory.projects.global")}
          </span>
          <span className="ml-auto shrink-0 text-xs text-text-muted">{counts}</span>
        </summary>
        <ul className="flex flex-col gap-0.5 border-t border-border-subtle px-3 py-2 pl-9">
          {row.items.map((i) => (
            <li key={i.entry} className="flex items-center gap-2 text-xs">
              <span className={i.action === "remove" ? "w-12 shrink-0 text-warning" : "w-12 shrink-0 text-text-muted"}>
                {t(`memory.preview.action.${i.action}`)}
              </span>
              {onOpenMemory && i.action !== "remove" ? (
                <button
                  type="button"
                  className="min-w-0 truncate text-left hover:underline"
                  onClick={() => onOpenMemory(i.entry, row.project)}
                >
                  {i.title}
                </button>
              ) : (
                <span className="min-w-0 truncate">{i.title}</span>
              )}
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

function BlockedAgents({ agents }: { agents: readonly SyncAgent[] }) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {agents.map((a) => (
        <li key={a.agent_type} className="flex flex-wrap items-center gap-2">
          <AgentBadge type={a.agent_type} name={agentTypeLabel(a.agent_type)} size="sm" showName />
          <span className="text-xs text-text-muted">
            {a.writer.state === "off"
              ? t("memory.needsYou.agentOff", { agent: agentTypeLabel(a.agent_type) })
              : a.writer.reason}
          </span>
          <Button variant="link" size="sm" className="ml-auto" asChild>
            <Link to={agentTabPath(a.agent_type, "memory")}>
              {t("memory.needsYou.openAgent", { agent: agentTypeLabel(a.agent_type) })}
              <ChevronRight aria-hidden />
            </Link>
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function MemoryNeedsYou({ preview, failures, withheld, agents, onOpenMemory }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const write = useWritePreview();
  const cancel = useCancelPreview();
  const busy = write.isPending || cancel.isPending;

  const blocked = agents.filter((a) => a.writer.state !== "ok");
  const parts = [
    preview ? t("memory.needsYou.preview", { count: preview.copies }) : null,
    failures.length ? t("memory.needsYou.failed", { count: failures.length }) : null,
    withheld.length ? t("memory.needsYou.withheld", { count: withheld.length }) : null,
    blocked.length ? t("memory.needsYou.blocked", { count: blocked.length }) : null,
  ].filter((p): p is string => p !== null);
  if (parts.length === 0) return null;

  return (
    <>
      <div
        role="status"
        data-testid="memory-needs-you"
        className="flex items-center gap-3 rounded-xl border border-warning/30 bg-warning-soft px-3.5 py-2.5"
      >
        <CircleAlert className="size-[15px] shrink-0 text-warning" aria-hidden />
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="text-sm font-semibold text-text">
            {t("memory.needsYou.title", { count: parts.length })}
          </p>
          <p className="text-xs text-text-muted">{parts.join(" · ")}</p>
        </div>
        <Button variant="outline" size="sm" className="ml-auto" onClick={() => setOpen(true)}>
          {t("memory.needsYou.review")}
        </Button>
      </div>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        title={t("memory.needsYou.title", { count: parts.length })}
        footer={
          preview ? (
            <>
              <Button variant="ghost" disabled={busy} onClick={() => cancel.mutate()}>
                {t("memory.preview.cancel")}
              </Button>
              <Button
                loading={write.isPending}
                disabled={busy}
                onClick={() => write.mutate(undefined, { onSuccess: () => setOpen(false) })}
              >
                {t("memory.preview.write", { count: preview.copies })}
              </Button>
            </>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-6">
          {preview ? (
            <Block title={t("memory.preview.title", { count: preview.copies })}>
              <p className="text-xs text-text-muted">{t("memory.preview.description")}</p>
              <ul className="flex flex-col gap-2">
                {preview.rows.map((r) => (
                  <PreviewGroup
                    key={`${r.agent}:${r.project}`}
                    row={r}
                    onOpenMemory={
                      onOpenMemory
                        ? (entry, project) => {
                            setOpen(false);
                            onOpenMemory(entry, project);
                          }
                        : undefined
                    }
                  />
                ))}
              </ul>
            </Block>
          ) : null}
          {failures.length ? (
            <Block title={t("memory.problems.failed", { count: failures.length })}>
              <p className="text-xs text-text-muted">{t("memory.problems.failedKept")}</p>
              <Problems items={failures} reason />
            </Block>
          ) : null}
          {withheld.length ? (
            <Block title={t("memory.problems.withheld", { count: withheld.length })}>
              <p className="text-xs text-text-muted">{t("memory.problems.withheldBody")}</p>
              <Problems items={withheld} reason={false} />
            </Block>
          ) : null}
          {blocked.length ? (
            <Block title={t("memory.needsYou.agentOffTitle")}>
              <BlockedAgents agents={blocked} />
            </Block>
          ) : null}
        </div>
      </Drawer>
    </>
  );
}
