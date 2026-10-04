// frontend/src/pages/sync/SyncHeader.tsx — the Sync page's header (every 6.5 board).
//
// One row: "Sync", the Experimental tag, the status pill, and the primary
// action on the right — always "Sync now" (6.4 Status group), "Syncing…" and
// disabled while a round runs. Under it the description line is the remote:
// "Keeps this vault in step with <url> [copy] · main · every hour". A Mac that
// is not set up shows "Not set up", the setup lead and no action — the body
// below is the setup flow, which has its own buttons.
import { useTranslation } from "react-i18next";
import { Check, Copy, RefreshCw } from "lucide-react";

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
    <span className="flex flex-wrap items-center gap-x-1">
      <span>{t("sync.header.keeps")}</span>
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
    </span>
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
    <PageHeader
      title={t("sync.title")}
      experimental
      subtitle={
        setUp && remote ? <RemoteLine remote={remote} /> : setUp ? undefined : t("sync.setup.lead")
      }
      badges={<SyncPill state={state} />}
      actions={
        setUp ? (
          <Button type="button" onClick={onRun} disabled={action.disabled} loading={action.syncing}>
            <RefreshCw aria-hidden />
            {t(action.syncing ? "sync.header.syncing" : "sync.header.syncNow")}
          </Button>
        ) : undefined
      }
    />
  );
}
