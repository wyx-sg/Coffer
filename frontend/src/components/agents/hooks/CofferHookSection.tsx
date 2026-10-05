// src/components/agents/hooks/CofferHookSection.tsx — Coffer's memory hook, as the Hooks tab's first section (boards 2.1.34–39).
//
// One block of properties: State, Command, Events (tags — one hook sits on
// several events) and File. The fix sits at the title's right: Repair (it opens
// the Review changes flow) when the hook is out of date or missing; Check again
// when the agent has not approved it, or it has never fired (with a link to
// Activity, where every fire is logged). The sentence under the title says why.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { RefreshCw, Wrench } from "lucide-react";

import { FileLink } from "@/components/agents/hooks/FileLink";
import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { cofferEvents, cofferHookState, timeAgo } from "@/lib/agents/hookRows";
import type { CofferHook } from "@/lib/api/agents";

interface Props {
  hook: CofferHook;
  agentType: string;
  /** Opens the Review changes flow that rewrites the hook; Repair shows only when given. */
  onRepair?: () => void;
  onCheckAgain: () => void;
  checking: boolean;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[172px_minmax(0,1fr)] items-center gap-4 border-t border-border-subtle py-3">
      <dt className="text-sm font-medium text-text">{label}</dt>
      <dd className="min-w-0 text-sm text-text-muted">{children}</dd>
    </div>
  );
}

export function CofferHookSection({ hook, agentType, onRepair, onCheckAgain, checking }: Props) {
  const { t, i18n } = useTranslation();
  const state = cofferHookState(hook);
  const agent = agentTypeLabel(agentType);
  const events = cofferEvents(hook);
  const file = abbreviateHomePath(hook.path);
  const firedAt = hook.last_fired_at;

  const reason = (() => {
    switch (state.word) {
      case "current":
        return t("agents.hooks.coffer.reason.current", { count: events.length });
      case "stale":
        return t("agents.hooks.coffer.reason.stale");
      case "missing":
        return t("agents.hooks.coffer.reason.missing", { file, agent });
      case "untrusted":
        return t("agents.hooks.coffer.reason.untrusted", { agent });
      case "modified":
        return t("agents.hooks.coffer.reason.modified", { agent });
      case "disabled":
        return t("agents.hooks.coffer.reason.disabled", { agent });
      case "neverFired":
        return t(
          `agents.hooks.coffer.reason.neverFired.${agentType === "codex" ? "codex" : "claude_code"}`,
          {
            agent,
            file,
          },
        );
    }
  })();

  const fired = firedAt
    ? t(state.word === "missing" ? "agents.hooks.coffer.lastFired" : "agents.hooks.coffer.fired", {
        time: timeAgo(firedAt, i18n.language),
      })
    : state.word === "untrusted"
      ? t("agents.hooks.coffer.neverFiredSub")
      : null;

  const fix = state.repair ? (
    onRepair ? (
      <Button size="sm" onClick={onRepair}>
        <Wrench aria-hidden /> {t("agents.hooks.coffer.repair")}
      </Button>
    ) : null
  ) : state.word !== "current" ? (
    <>
      {state.word === "neverFired" ? (
        <Link
          to="/activity"
          className="text-xs font-medium text-accent-text underline-offset-4 hover:underline"
        >
          {t("agents.hooks.coffer.viewActivity")}
        </Link>
      ) : null}
      <Button variant="outline" size="sm" disabled={checking} onClick={onCheckAgain}>
        <RefreshCw aria-hidden /> {t("agents.hooks.coffer.checkAgain")}
      </Button>
    </>
  ) : null;

  return (
    <Section
      as="h2"
      title={t("agents.hooks.coffer.title")}
      actions={fix}
      gap="tight"
      testId="coffer-hook-section"
    >
      <p className="mb-1 text-xs text-text-muted">{reason}</p>
      <dl className="flex flex-col">
        <Row label={t("agents.hooks.coffer.state")}>
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <StatusWord tone={state.tone}>{t(`agents.hooks.state.${state.word}`)}</StatusWord>
            {fired ? <span className="text-xs text-text-subtle">{fired}</span> : null}
          </span>
        </Row>
        <Row label={t("agents.hooks.coffer.command")}>
          <span className="break-all font-mono text-xs text-text">
            {state.word === "missing" ? "—" : (hook.installed_command ?? hook.expected_command)}
          </span>
        </Row>
        <Row label={t("agents.hooks.coffer.events")}>
          <span className="flex flex-wrap gap-1">
            {events.map((e) => (
              <span
                key={e}
                className="rounded-xs bg-surface-sunken px-1.5 py-0.5 text-2xs font-medium text-text-muted"
              >
                {e}
              </span>
            ))}
          </span>
        </Row>
        <Row label={t("agents.hooks.coffer.file")}>
          <FileLink path={hook.path} />
        </Row>
      </dl>
    </Section>
  );
}
