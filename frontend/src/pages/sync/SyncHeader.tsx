// frontend/src/pages/sync/SyncHeader.tsx — the Sync page's header (every 6.5 board).
//
// One row: "Sync", the "?" that explains adding another Mac, the status pill,
// and the primary action on the right ("Sync now", "Syncing…", or "Try again"
// when the last round could not reach or sign in to the remote). Under it the
// remote itself: its URL in mono with a copy button, the branch, and how often
// a round runs. A Mac that is not set up shows "Not set up" and no action —
// the body below is the setup flow, which has its own buttons.
import { useTranslation } from "react-i18next";
import { Check, Copy, RefreshCw, RotateCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import type { SyncRemote } from "@/lib/api/sync";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { primaryAction, type SyncState } from "./syncPageState";
import { intervalPhrase } from "./syncTime";

/** The pill in the header: a status tone, or the accent while something moves. */
function SyncPill({ state }: { state: SyncState }) {
  const { t } = useTranslation();
  const label = t(`sync.pill.${state.kind}`, { count: state.count });
  if (state.tone === "info") {
    return (
      <span
        data-testid="sync-pill"
        className="inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-item bg-accent-soft px-2 text-xs font-semibold text-accent-text"
      >
        <span aria-hidden className="inline-block size-1.5 shrink-0 rounded-full bg-accent" />
        {label}
      </span>
    );
  }
  return (
    <span data-testid="sync-pill" className="inline-flex">
      <StatusPill tone={state.tone}>{label}</StatusPill>
    </span>
  );
}

function RemoteLine({ remote }: { remote: SyncRemote }) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();
  return (
    <p className="flex flex-wrap items-center gap-x-1 text-sm text-text-subtle">
      <span className="whitespace-nowrap font-mono text-xs text-text-muted">{remote.url}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="size-[22px]"
        aria-label={t("sync.header.copyUrl")}
        title={t("sync.header.copyUrl")}
        onClick={() => copy(remote.url)}
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
      <span>
        · {remote.branch} · {intervalPhrase(remote.interval_seconds, t)}
      </span>
    </p>
  );
}

interface Props {
  state: SyncState;
  remote: SyncRemote | null;
  onRun: () => void;
}

export function SyncHeader({ state, remote, onRun }: Props) {
  const { t } = useTranslation();
  const action = primaryAction(state.kind);
  const setUp = state.kind !== "setup";
  return (
    <div className="flex flex-col gap-1">
      <PageHeader
        title={t("sync.title")}
        subtitle={t("sync.subtitle")}
        badges={<SyncPill state={state} />}
        actions={
          setUp ? (
            <Button
              type="button"
              variant="outline"
              onClick={onRun}
              disabled={action.disabled}
              loading={action.label === "syncing"}
            >
              {action.label === "tryAgain" ? <RotateCw aria-hidden /> : <RefreshCw aria-hidden />}
              {t(`sync.header.${action.label}`)}
            </Button>
          ) : undefined
        }
      />
      {remote ? <RemoteLine remote={remote} /> : null}
    </div>
  );
}
