// frontend/src/components/agents/AgentMemoryCopies.tsx
//
// The **Copies Coffer wrote here** row of an agent's Memory sync section (spec
// memory "Show on each agent what Coffer wrote into it"): per place
// Coffer writes into, how many copies it holds and how many the agent edited
// or removed, or why it cannot write there. Claude Code gets text, not copies,
// so its row says so.
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SyncAgent } from "@/lib/api/memoryTypes";

type Writer = SyncAgent["writer"];
type CopyCounts = SyncAgent["copies"];

/** What Coffer holds in one place it writes into, or why it cannot write there. */
function CopiesIn({
  writer,
  copies,
  asText = false,
}: {
  writer: Writer;
  copies: CopyCounts;
  asText?: boolean;
}) {
  const { t } = useTranslation();
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
  // Claude Code gets text (a block in each project's MEMORY.md), no copies to count.
  if (asText && !copies.written && !edited && !removed) {
    return <span className="text-sm">{t("memory.agents.asText")}</span>;
  }
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

/** The copies: one line per memory folder when the agent has more than one
 *  (Codex's `memories/` and `memories_v2/`), each with its own state, so a
 *  folder Coffer cannot write into shows beside the ones it can. */
export function AgentMemoryCopies({ agent }: { agent: SyncAgent }) {
  const locations = agent.locations ?? [];
  if (locations.length <= 1)
    return (
      <CopiesIn
        writer={agent.writer}
        copies={agent.copies}
        asText={agent.agent_type === "claude_code"}
      />
    );
  return (
    <ul className="flex flex-col gap-2" data-testid="memory-sync-locations">
      {locations.map((loc) => (
        <li key={loc.path} className="flex flex-col gap-0.5">
          <span className="font-mono text-xs text-text-muted [overflow-wrap:anywhere]">
            {abbreviateHomePath(loc.path)}
          </span>
          <CopiesIn writer={loc.writer} copies={loc.copies ?? {}} />
        </li>
      ))}
    </ul>
  );
}
