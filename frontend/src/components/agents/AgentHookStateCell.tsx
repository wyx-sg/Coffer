// src/components/agents/AgentHookStateCell.tsx — the State cell of one Hooks-tab row.
//
// The agent's own hooks read "Active": the listing has no per-hook fire record,
// so nothing more is claimed for them. Coffer's hook reads its health, trust or
// fire state (lib/agents/hookRows `cofferHookState`), with when it last fired.
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { cofferHookState, timeAgo, type HookRow } from "@/lib/agents/hookRows";

export function AgentHookStateCell({ row }: { row: HookRow }) {
  const { t, i18n } = useTranslation();
  if (!row.coffer) return <StatusWord tone="ok">{t("agents.hooksTab.state.active")}</StatusWord>;

  const state = cofferHookState(row.coffer);
  const firedAt = row.coffer.last_fired_at;
  const showFired = firedAt && (state.word === "current" || state.word === "stale");
  return (
    <span className="flex flex-col gap-0.5">
      <StatusWord tone={state.tone}>{t(`agents.hooksTab.state.${state.word}`)}</StatusWord>
      {showFired ? (
        <span className="text-2xs text-text-muted">
          {t("agents.hooksTab.fired", { time: timeAgo(firedAt, i18n.language) })}
        </span>
      ) : state.word === "untrusted" ? (
        <span className="text-2xs text-text-muted">{t("agents.hooksTab.untrustedSub")}</span>
      ) : null}
    </span>
  );
}
