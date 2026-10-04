// frontend/src/pages/sync/SyncProblemParts.tsx — the pieces every sync
// problem card is built from (SyncProblemBanner): git's message, shown or
// folded away, and the backend's hand-off.
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import type { SyncProblem } from "@/lib/api/sync";

export function GitMessage({ message }: { message: string }) {
  return (
    <pre className="whitespace-pre-wrap break-words rounded-lg bg-surface-sunken px-3 py-2.5 font-mono text-xs text-text">
      {message}
    </pre>
  );
}

/** Git's words, folded away: the sentence above already says what happened. */
export function GitMessageDisclosure({ message }: { message: string }) {
  const { t } = useTranslation();
  if (!message) return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none text-text-subtle hover:text-text">
        {t("sync.problem.showMessage")}
      </summary>
      <div className="mt-1.5">
        <GitMessage message={message} />
      </div>
    </details>
  );
}

export function Handoff({ problem }: { problem: SyncProblem }) {
  return problem.handoff ? <AgentHandoff prompt={problem.handoff.prompt} size="sm" /> : null;
}

export function Body({ children }: { children: React.ReactNode }) {
  return <p className="max-w-prose text-sm text-text-muted">{children}</p>;
}

/** A card's button row, a little apart from the text above it. */
export function Actions({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2 pt-1">{children}</div>;
}
