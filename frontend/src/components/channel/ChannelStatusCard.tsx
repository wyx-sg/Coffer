// frontend/src/components/channel/ChannelStatusCard.tsx
// The channel's live state: the adapter, the machine whose daemon runs it, and
// the paired owner.
//
// The binding is a ROW here rather than a card of its own. It is the other half
// of the adapter row's headline — "Stopped" on a channel bound elsewhere is not
// a fault to chase, and "Running" is only believable on the machine that is
// bound — and a second card put one question's two halves under two headings.
//
// Split from ChannelDetailCards for file size once the row moved in.
import { useTranslation } from "react-i18next";
import { Activity } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ChannelStatus } from "@/lib/api/channels";
import { useMachines } from "@/lib/hooks/useMachines";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { bindingState } from "./channelBinding";
import { ChannelMachineSelect } from "./ChannelMachineSelect";
import { RunStateBadge, StatusRow } from "./ChannelDetailCards";

export function ChannelStatusCard({
  name,
  config,
  status,
}: {
  name: string;
  /** The channel's current config, carried through the rebind PATCH. */
  config: Record<string, unknown>;
  status: ChannelStatus | undefined;
}) {
  const { t } = useTranslation();
  const { data: machineList } = useMachines();
  const { data: syncStatus } = useSyncStatus();

  // The status is authoritative for the binding; the config is the fallback
  // that lets the row render before the first status lands.
  const runsOn = status?.runs_on ?? (config.runs_on as string | undefined) ?? null;
  const binding = bindingState(runsOn, {
    selfId: syncStatus?.machine_id ?? null,
    known: (machineList?.machines ?? []).map((m) => m.machine_id),
    runsHere: status?.runs_here,
  });
  // The two binding states that are somebody's mistake rather than somebody's
  // choice (FR-080): bound to nobody, and bound to a machine the registry no
  // longer knows. Both run nowhere here, and they must be told apart — "not
  // running" alone sends the reader hunting for a crash that never happened.
  const machineFault =
    binding === "unbound"
      ? t("channels.machine.unboundBody")
      : binding === "unknown"
        ? t("channels.machine.unknownBody", { id: runsOn })
        : null;
  return (
    <Card className="paper-card" data-testid="channel-status-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Activity className="size-4 text-primary" aria-hidden />
          {t("channels.status.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {status === undefined ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          <>
            <StatusRow
              label={t("channels.status.adapter")}
              value={<RunStateBadge running={status.running} />}
            />
            {/* Directly under the adapter row, because it is the other half of
                that row's headline: "Stopped" on a channel bound elsewhere is
                not a fault to chase, and "Running" is only believable on the
                machine that is bound. */}
            <StatusRow
              label={t("channels.machine.title")}
              value={
                <ChannelMachineSelect
                  name={name}
                  config={config}
                  runsOn={runsOn}
                  runsHere={status.runs_here}
                />
              }
            />
            {status.peer === null ? (
              <StatusRow
                label={t("channels.status.peer")}
                value={<span className="text-muted-foreground">{t("channels.notPaired")}</span>}
              />
            ) : (
              <>
                <StatusRow
                  label={t("channels.status.peer")}
                  value={<span className="font-medium">{status.peer.display_name}</span>}
                />
                <StatusRow
                  label={t("channels.status.chatId")}
                  value={<code className="text-xs">{status.peer.chat_id}</code>}
                />
                <StatusRow
                  label={t("channels.status.pairedAt")}
                  value={formatDateTime(status.peer.paired_at)}
                />
                <StatusRow
                  label={t("channels.status.conversation")}
                  value={
                    status.peer.active_conversation_id !== null ? (
                      <code className="text-xs">{status.peer.active_conversation_id}</code>
                    ) : (
                      <span className="text-muted-foreground">{t("channels.status.none")}</span>
                    )
                  }
                />
              </>
            )}
            {machineFault ? (
              <p
                role="alert"
                className="mt-2 rounded border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn"
              >
                {machineFault}
              </p>
            ) : null}
            {status.pending_pairing ? (
              <p className="pt-1 text-xs text-muted-foreground">
                {t("channels.status.pendingPairing")}
              </p>
            ) : null}
            {(status.diagnostics ?? []).map((diagnostic) => (
              // FR-060: a setting that reads correctly here and does nothing in
              // the chat — the one case worth interrupting the status list for.
              <p
                key={diagnostic.code}
                role="alert"
                className="mt-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
              >
                {diagnostic.message}
              </p>
            ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Generate-pairing-code button + the LARGE code with expiry and copy. */
