// src/components/custom-tools/ReviewGroupPanel.tsx — the left column of Import's review: the group as it will
// be made (name, base URL, headers, reach), then the tools that become tools and the ones skipped. A tool
// is chosen to read its spec text in the viewer on the right.
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Badge } from "@/components/ui/badge";
import { useAgents } from "@/lib/hooks/useAgents";
import { operationChangesData, type Operation } from "@/lib/customTools/operations";
import { chosenAgents, pickableAgents } from "@/lib/reach/reachState";
import { cn } from "@/lib/utils";
import type { GroupDraft } from "./addFlow";

/** How many skipped operations are named before "and N more". */
const SKIPPED_SHOWN = 4;

const LABEL = "text-2xs font-semibold uppercase tracking-wide text-text-subtle";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-[30px] grid-cols-[84px_minmax(0,1fr)] items-center gap-3 border-t border-border-subtle py-0.5 first:border-t-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex min-w-0 items-center gap-2 text-sm">{children}</span>
    </div>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return <span className="truncate font-mono text-xs text-text">{children}</span>;
}

function Reach({ group }: { group: GroupDraft }) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const { mode, scope } = group.reach;
  if (mode === "disabled") return <>{t("scope.off")}</>;
  if (mode === "everywhere") return <>{t("scope.everywhere")}</>;
  const chosen = chosenAgents(scope, pickableAgents(agents));
  if (chosen.length === 0) return <>{t("scope.noneSelected")}</>;
  return (
    <span className="inline-flex gap-[3px]">
      {chosen.map((a) => (
        <AgentBadge key={a.uid} type={a.type} name={a.name} size="sm" />
      ))}
    </span>
  );
}

interface ToolRowProps {
  op: Operation;
  selected: boolean;
  skipped?: boolean;
  onSelect: () => void;
}

function ToolRow({ op, selected, skipped, onSelect }: ToolRowProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left",
        selected ? "bg-surface-raised ring-1 ring-border" : "hover:bg-surface-hover",
      )}
    >
      <span className="flex min-w-0 flex-1 flex-col gap-px">
        <span
          className={cn("truncate font-mono text-xs", skipped ? "text-text-muted" : "text-text")}
        >
          {op.tool.name}
        </span>
        <span className="truncate font-mono text-2xs text-text-muted">
          {op.tool.method ?? "GET"} {op.tool.path}
        </span>
      </span>
      {skipped && operationChangesData(op) ? (
        <Badge variant="warning">{t("customTools.tools.changesData")}</Badge>
      ) : null}
    </button>
  );
}

interface Props {
  group: GroupDraft;
  tools: Operation[];
  skipped: Operation[];
  /** The operation whose spec text is open. */
  selected: string | null;
  onSelect: (key: string) => void;
}

export function ReviewGroupPanel({ group, tools, skipped, selected, onSelect }: Props) {
  const { t } = useTranslation();
  const headers = group.headers.filter((h) => h.key.trim() !== "");
  return (
    <div className="flex min-h-0 flex-col gap-2.5 overflow-y-auto rounded-lg bg-surface-sunken p-3">
      <span className={LABEL}>{t("customTools.import.groupTitle")}</span>
      <div className="flex flex-col">
        <Row label={t("customTools.import.name")}>
          <Mono>{group.name}</Mono>
        </Row>
        <Row label={t("customTools.fields.baseUrl")}>
          <Mono>{group.baseUrl}</Mono>
        </Row>
        <Row label={t("customTools.fields.headers")}>
          {headers.length === 0 ? (
            <span className="text-xs text-text-muted">{t("customTools.import.noHeaders")}</span>
          ) : (
            <span className="flex min-w-0 flex-wrap gap-1.5">
              {headers.map((h, i) => (
                <span
                  key={i}
                  className="inline-flex h-[22px] items-center gap-1.5 rounded-md border border-border-subtle bg-surface-raised px-[7px] font-mono text-xs"
                >
                  {h.value.kind === "plain" ? null : <KeyRound className="size-3" aria-hidden />}
                  {h.value.kind === "plain" ? h.key : h.value.name}
                </span>
              ))}
            </span>
          )}
        </Row>
        <Row label={t("customTools.fields.availableTo")}>
          <Reach group={group} />
        </Row>
      </div>
      <section aria-label={t("customTools.list.toolCount", { count: tools.length })}>
        <span className={LABEL}>
          {t("customTools.list.toolCount", { count: tools.length })}
        </span>
        <div className="mt-1.5 flex flex-col gap-0.5">
          {tools.map((op) => (
            <ToolRow
              key={op.key}
              op={op}
              selected={selected === op.key}
              onSelect={() => onSelect(op.key)}
            />
          ))}
        </div>
      </section>
      {skipped.length > 0 ? (
        <section aria-label={t("customTools.import.skipped", { count: skipped.length })}>
          <span className={LABEL}>
            {t("customTools.import.skipped", { count: skipped.length })}
          </span>
          <div className="mt-1.5 flex flex-col gap-0.5">
            {skipped.slice(0, SKIPPED_SHOWN).map((op) => (
              <ToolRow
                key={op.key}
                op={op}
                skipped
                selected={selected === op.key}
                onSelect={() => onSelect(op.key)}
              />
            ))}
            {skipped.length > SKIPPED_SHOWN ? (
              <p className="px-2 py-1 text-xs text-text-muted">
                {t("customTools.import.moreSkipped", { count: skipped.length - SKIPPED_SHOWN })}
              </p>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
