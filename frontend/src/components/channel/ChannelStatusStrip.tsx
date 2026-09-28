// frontend/src/components/channel/ChannelStatusStrip.tsx
// The top of the channel card: one line that answers "is it live, and where?"
// — the adapter's run state, for SeaTalk the websocket connection, and the
// machine that runs it — with the faults, and only the faults, underneath.
//
// The three sit on one line because they are one question. "Stopped" on a
// channel bound elsewhere is not a fault to chase, and "Running" is only
// believable next to the machine that is bound; a SeaTalk channel's connection
// is the rest of its health answer (spec channels/seatalk "Report the websocket
// connection as the channel's inbound state") — there is no listener, port, URL
// or tunnel to show, and nothing to probe.
//
// Everything that is explanation rather than state lives behind the machine
// label's "?" (MachineBindingHelp). What stays inline under the strip is what
// the reader has to act on: a binding that runs nowhere, the connection's last
// error verbatim, the daemon's own diagnostics, and an outstanding pairing code.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { ChannelStatus, InboundInfo, WebSocketState } from "@/lib/api/channels";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { toneClass, type Tone } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { bindingState } from "./channelBinding";
import { channelHealthClass } from "./channelHealth";
import { ChannelMachineSelect, MachineBindingHelp } from "./ChannelMachineSelect";

const ALERT_CLASS = "rounded-md border px-3 py-2 text-xs";
const ERROR_ALERT = cn(ALERT_CLASS, "border-destructive/40 bg-destructive/10 text-destructive");
const WARN_ALERT = cn(ALERT_CLASS, "border-status-warn/40 bg-status-warn/5 text-status-warn");

/** Running / stopped pill, on the one tone mapping the list badge uses too. */
function RunStateBadge({ running }: { running: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" className={cn("border-transparent", channelHealthClass(running))}>
      {running ? t("channels.status.running") : t("channels.status.stopped")}
    </Badge>
  );
}

/** A live socket is the only healthy state; a failed one is an error. */
function connectionTone(state: WebSocketState | null): Tone {
  if (state === "connected") return "ok";
  if (state === "kicked" || state === "sdk_missing" || state === "error") return "error";
  return "warn";
}

function ConnectionBadge({ inbound }: { inbound: InboundInfo }) {
  const { t } = useTranslation();
  const state = inbound.websocket_state;
  return (
    <Badge variant="outline" className={cn("border-transparent", toneClass(connectionTone(state)))}>
      {t(`channels.inbound.state.${state ?? "unknown"}`)}
    </Badge>
  );
}

/** A label and its value, as one unbreakable item of the wrapping strip. */
function StripItem({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

export function ChannelStatusStrip({
  uid,
  name,
  config,
  status,
}: {
  /** The channel — what the rebind PATCH is addressed to. */
  uid: string;
  /** Its label, which names the machine picker for assistive tech. */
  name: string;
  /** The channel's current config, carried through the rebind PATCH. */
  config: Record<string, unknown>;
  status: ChannelStatus;
}) {
  const { t } = useTranslation();
  const { data: machineList } = useMachines();
  const { machineId: selfId } = useThisMachineId();

  // The status is authoritative for the binding; the config is the fallback.
  const runsOn = status.runs_on ?? (config.runs_on as string | undefined) ?? null;
  const binding = bindingState(runsOn, {
    selfId,
    known: (machineList?.machines ?? []).map((m) => m.machine_id),
    runsHere: status.runs_here,
  });
  // The two binding states that are somebody's mistake rather than somebody's
  // choice (see "Bind each channel to the one machine that runs it"): bound to nobody, and bound to
  // a machine the registry no longer knows. Both run nowhere here, and they must be told apart —
  // "not running" alone sends the reader hunting for a crash that never happened.
  const machineFault =
    binding === "unbound"
      ? t("channels.machine.unboundBody")
      : binding === "unknown"
        ? t("channels.machine.unknownBody", { id: runsOn })
        : null;

  return (
    <div className="space-y-3" data-testid="channel-status-strip">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <StripItem label={t("channels.status.adapter")}>
          <RunStateBadge running={status.running} />
        </StripItem>
        {status.inbound ? (
          <StripItem label={t("channels.inbound.title")}>
            <ConnectionBadge inbound={status.inbound} />
          </StripItem>
        ) : null}
        <StripItem
          label={
            <>
              {t("channels.machine.title")}
              <MachineBindingHelp />
            </>
          }
        >
          <ChannelMachineSelect
            uid={uid}
            name={name}
            config={config}
            runsOn={runsOn}
            runsHere={status.runs_here}
            compact
          />
        </StripItem>
      </div>
      {machineFault ? (
        <p role="alert" className={WARN_ALERT}>
          {machineFault}
        </p>
      ) : null}
      {status.inbound?.websocket_error ? (
        <p role="alert" className={ERROR_ALERT}>
          {status.inbound.websocket_error}
        </p>
      ) : null}
      {(status.diagnostics ?? []).map((diagnostic) => (
        // spec channels/telegram "Report privacy mode that defeats the group
        // configuration": a setting that reads correctly here and does nothing in
        // the chat — the one case worth interrupting the card for.
        <p key={diagnostic.code} role="alert" className={ERROR_ALERT}>
          {diagnostic.message}
        </p>
      ))}
      {status.pending_pairing ? (
        <p className="text-xs text-muted-foreground">{t("channels.status.pendingPairing")}</p>
      ) : null}
    </div>
  );
}
