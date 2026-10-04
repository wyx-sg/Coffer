// frontend/src/components/knowledge/KnowledgeWriterMark.tsx
//
// The small tile every change, version and item carries before its writer's
// name (boards 5.1.03, 5.1.07, 5.1.26): an agent's official mark on its
// AgentBadge tile, curation's merge glyph on the accent tile, sync's and an
// edit on disk's glyphs on the neutral tile, and you on the neutral tile. One
// component so the timeline, History and the Inbox draw the same writer the
// same way.
import { useTranslation } from "react-i18next";
import { GitMerge, HardDrive, RefreshCw, User } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { cn } from "@/lib/utils";

interface Props {
  /** `user`, `agent`, `curation`, `sync` or `disk`. */
  writer: string;
  /** For `agent`: the agent's type or resource name (`claude-code`, `codex`). */
  agent?: string | null;
}

const TILE = "inline-flex h-[18px] w-[22px] shrink-0 items-center justify-center rounded-sm";

export function KnowledgeWriterMark({ writer, agent }: Props) {
  const { t } = useTranslation();
  if (writer === "agent" && agent && agent !== "agent" && agent !== "user") {
    return <AgentBadge type={agent.replace(/-/g, "_")} size="sm" />;
  }
  if (writer === "curation") {
    return (
      <span
        className={cn(TILE, "bg-accent-soft text-accent-text")}
        title={t("knowledge.writer.curation")}
        aria-label={t("knowledge.writer.curation")}
      >
        <GitMerge className="size-[11px]" aria-hidden />
      </span>
    );
  }
  const Icon = writer === "sync" ? RefreshCw : writer === "disk" ? HardDrive : User;
  const label =
    writer === "sync"
      ? t("knowledge.writer.sync")
      : writer === "disk"
        ? t("knowledge.writer.disk")
        : writer === "agent"
          ? t("knowledge.writer.agent")
          : t("knowledge.writer.user");
  return (
    <span className={cn(TILE, "bg-chip text-text-muted")} title={label} aria-label={label}>
      <Icon className="size-[11px]" aria-hidden />
    </span>
  );
}
