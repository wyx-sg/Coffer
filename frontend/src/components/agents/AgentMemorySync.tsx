// frontend/src/components/agents/AgentMemorySync.tsx
//
// The agent's part in the memory sync, on its Memory tab (spec memory "Show
// each agent's own curation and ask it to curate now"): one row per fact —
// whether its own memory is on (Coffer writes into it only then), whether its
// own curation is on (for Claude Code's Auto Dream, whether the person's own
// setting or the account default says so, when it last ran here, and **Turn
// on**, which writes the setting after a confirm), each with a hint to turn it
// on, and the copies Coffer
// wrote into it here (and how many the agent has since edited or removed), or
// why Coffer cannot write into it. For Codex, the person's answer to "Codex
// imports Claude Code's memories itself". **Curate now** (Claude Code only:
// Codex consolidates on its own whenever its memories are on) opens the agent
// in the person's terminal with the daemon's prompt to consolidate the memory
// folders Coffer wrote into, so they watch and confirm each change; **Open
// Memory** opens the Memory page filtered to what this agent remembered.
// Shown only while the memory feature is on.
import { ChevronRight, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { CodexImportSetting } from "@/components/memory/CodexImportSetting";
import { RelativeTime } from "@/components/RelativeTime";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { Section } from "@/components/Section";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { SyncAgent } from "@/lib/api/memoryTypes";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useCurateNow, useEnableCuration, useMemorySyncState } from "@/lib/hooks/useMemory";
import type { StatusTone } from "@/lib/statusTone";

/** The two settings each agent's own memory has, per agent type. */
const KNOWN_TYPES = new Set(["claude_code", "codex"]);
const typeKey = (type: string) => (KNOWN_TYPES.has(type) ? type : "other");

const SWITCH_TONE: Record<string, StatusTone> = { on: "ok", off: "warn", unknown: "off" };
const switchWord = (value: string) => (value in SWITCH_TONE ? value : "unknown");

interface Props {
  agentType: string;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] items-start gap-4 border-b border-border-subtle py-3 last:border-b-0">
      <span className="text-sm text-text-muted">{label}</span>
      <div className="flex min-w-0 flex-col gap-0.5">{children}</div>
    </div>
  );
}

function Setting({ agent, setting }: { agent: SyncAgent; setting: "memory" | "curation" }) {
  const { t } = useTranslation();
  const type = typeKey(agent.agent_type);
  const word = switchWord(agent.curation[setting]);
  // Curation only matters once the agent's own memory is on.
  const showHint = word !== "on" && (setting === "memory" || agent.curation.memory === "on");
  const hintKey =
    setting === "curation" && type === "claude_code" && word === "unknown"
      ? "curationUnknown"
      : setting;
  const source = setting === "curation" ? (agent.curation.source ?? "") : "";
  return (
    <Row label={t(`memory.agents.cols.${setting}`)}>
      <StatusWord tone={SWITCH_TONE[word]}>
        {t(`memory.agents.${setting}.${type}.${word}`)}
        {source ? ` · ${t(`memory.agents.curationSource.${source}`)}` : null}
      </StatusWord>
      {setting === "curation" && type === "claude_code" && agent.curation.memory === "on" ? (
        <LastCurated at={agent.curation.last_curated_at ?? ""} />
      ) : null}
      {showHint ? (
        <span className="text-xs text-text-muted">
          {t(`memory.agents.hint.${type}.${hintKey}`)}
        </span>
      ) : null}
      {setting === "curation" && type === "claude_code" && showHint ? (
        <EnableCuration agent={agent} />
      ) : null}
    </Row>
  );
}

function LastCurated({ at }: { at: string }) {
  const { t } = useTranslation();
  if (!at)
    return <span className="text-xs text-text-muted">{t("memory.agents.neverCurated")}</span>;
  return (
    <span className="text-xs text-text-muted">
      {t("memory.agents.lastCurated")} <RelativeTime iso={at} />
    </span>
  );
}

/** **Turn on**: Coffer writes Claude Code's Auto Dream setting, after a confirm. */
function EnableCuration({ agent }: { agent: SyncAgent }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const enable = useEnableCuration();
  const [confirming, setConfirming] = useState(false);
  const settings = abbreviateHomePath(`${agent.writer.path || "~/.claude"}/settings.json`);
  return (
    <div className="pt-1">
      <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
        {t("memory.agents.enableCuration.button")}
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        variant="default"
        title={t("memory.agents.enableCuration.title")}
        description={t("memory.agents.enableCuration.body", { path: settings })}
        confirmLabel={t("memory.agents.enableCuration.confirm")}
        errorTitle={t("memory.agents.enableCuration.failed")}
        pending={enable.isPending}
        error={enable.error}
        onConfirm={() =>
          enable.mutate(agent.agent_type, {
            onSuccess: (result) => {
              setConfirming(false);
              toast.success(
                t(`memory.agents.enableCuration.${result.changed ? "done" : "already"}`),
              );
            },
          })
        }
      />
    </div>
  );
}

function Copies({ agent }: { agent: SyncAgent }) {
  const { t } = useTranslation();
  const { writer, copies } = agent;
  if (writer.state !== "ok") {
    return (
      <div className="flex flex-col gap-0.5">
        <StatusWord tone={writer.state === "off" ? "off" : "warn"}>
          {t(`memory.agents.writer.${writer.state === "off" ? "off" : "blocked"}`)}
        </StatusWord>
        <span className="text-xs text-text-muted [overflow-wrap:anywhere]">
          {[writer.reason, writer.path && abbreviateHomePath(writer.path)]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
    );
  }
  const edited = copies.edited ?? 0;
  const removed = copies.removed ?? 0;
  const byAgent = [
    edited > 0 ? t("memory.agents.edited", { count: edited }) : null,
    removed > 0 ? t("memory.agents.removed", { count: removed }) : null,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-sm tabular-nums">
        {t("memory.agents.written", { count: copies.written ?? 0 })}
      </span>
      {byAgent.length > 0 ? (
        <span className="text-xs text-text-muted">{byAgent.join(" · ")}</span>
      ) : null}
    </div>
  );
}

export function AgentMemorySync({ agentType }: Props) {
  const { t } = useTranslation();
  const enabled = useFeatureEnabled("memory");
  const { data: state } = useMemorySyncState();
  const curate = useCurateNow();
  const agent = enabled ? state?.agents.find((a) => a.agent_type === agentType) : undefined;
  if (!agent || !state) return null;
  const name = agentTypeLabel(agent.agent_type);

  return (
    <Section
      as="h2"
      title={t("agents.memoryTab.sync.title")}
      gap="tight"
      testId="memory-sync-section"
      actions={
        <div className="flex items-center gap-2">
          {agent.agent_type === "claude_code" ? (
            <Button
              variant="outline"
              size="sm"
              aria-label={t("memory.agents.curateNowFor", { agent: name })}
              title={t("memory.agents.curateNowHint")}
              disabled={agent.curation.memory === "off" || curate.isPending}
              onClick={() => curate.mutate(agent.agent_type)}
            >
              <Sparkles aria-hidden /> {t("memory.agents.curateNow")}
            </Button>
          ) : null}
          <Button variant="link" size="sm" asChild>
            <Link to={`/memory?source=${encodeURIComponent(agent.agent_type)}`}>
              {t("agents.memoryTab.sync.open")} <ChevronRight aria-hidden />
            </Link>
          </Button>
        </div>
      }
    >
      <div className="rounded-lg border border-border-subtle px-4">
        <Setting agent={agent} setting="memory" />
        <Setting agent={agent} setting="curation" />
        <Row label={t("memory.agents.cols.copies")}>
          <Copies agent={agent} />
        </Row>
        {agent.agent_type === "codex" ? (
          <div className="py-1">
            <CodexImportSetting value={state.codex_imports_claude} />
          </div>
        ) : null}
      </div>
    </Section>
  );
}
