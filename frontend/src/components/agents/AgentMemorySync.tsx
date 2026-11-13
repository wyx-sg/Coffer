// frontend/src/components/agents/AgentMemorySync.tsx
//
// The agent's part in the memory sync, on its Memory tab (spec memory "Show
// on each agent what Coffer wrote into it"): the copies Coffer wrote into it
// here (and how many the agent has since edited or removed), or why Coffer
// cannot write into it, with how to turn the agent's own memory on when that
// is why; for Codex, one line per memory folder (`memories/`, `memories_v2/`,
// and any newer one Coffer cannot write into yet) and the person's answer to
// "Codex imports Claude Code's memories itself". **Open Memory** opens the
// Memory page filtered to what this agent remembered. The agent's own
// curation is its own business: nothing here shows or starts it. Shown only
// while the memory feature is on.
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentMemoryCopies as Copies } from "@/components/agents/AgentMemoryCopies";
import { CodexImportSetting } from "@/components/memory/CodexImportSetting";
import { Button } from "@/components/ui/button";
import { Section } from "@/components/Section";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useMemorySyncState } from "@/lib/hooks/useMemory";

const KNOWN_TYPES = new Set(["claude_code", "codex"]);
const typeKey = (type: string) => (KNOWN_TYPES.has(type) ? type : "other");

interface Props {
  agentType: string;
}

export function AgentMemorySync({ agentType }: Props) {
  const { t } = useTranslation();
  const enabled = useFeatureEnabled("memory");
  const { data: state } = useMemorySyncState();
  const agent = enabled ? state?.agents.find((a) => a.agent_type === agentType) : undefined;
  if (!agent || !state) return null;

  return (
    <Section
      as="h2"
      title={t("agents.memoryTab.sync.title")}
      gap="tight"
      testId="memory-sync-section"
      actions={
        <Button variant="link" size="sm" asChild>
          <Link to={`/memory?source=${encodeURIComponent(agent.agent_type)}`}>
            {t("agents.memoryTab.sync.open")} <ChevronRight aria-hidden />
          </Link>
        </Button>
      }
    >
      <div className="rounded-lg border border-border-subtle px-4">
        <div className="grid grid-cols-[180px_1fr] items-start gap-4 border-b border-border-subtle py-3 last:border-b-0">
          <span className="text-sm text-text-muted">{t("memory.agents.copies")}</span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <Copies agent={agent} />
            {agent.writer.state === "off" ? (
              <span className="text-xs text-text-muted">
                {t(`memory.agents.turnOn.${typeKey(agent.agent_type)}`)}
              </span>
            ) : null}
          </div>
        </div>
        {agent.agent_type === "codex" ? (
          <div className="py-1">
            <CodexImportSetting value={state.codex_imports_claude} />
          </div>
        ) : null}
      </div>
    </Section>
  );
}
