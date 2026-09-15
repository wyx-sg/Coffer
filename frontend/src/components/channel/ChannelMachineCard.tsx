// frontend/src/kinds/channel/ChannelMachineCard.tsx
// The detail page's answer to "where does this channel actually run?" (spec
// channels, "Where a channel runs"): the machine whose daemon holds this bot's
// one allowed connection, whether that machine is this one, and the picker
// that moves it.
//
// It sits beside the status card because it is the missing half of that card's
// headline: "Stopped" on a channel bound elsewhere is not a fault to chase,
// and "Running" is only believable on the machine that is bound. `runs_here`
// is read from the status rather than compared here — see channelBinding.ts.
//
// The card states the handover timing because it is the one thing a user
// cannot see and would otherwise discover as a bug: a rebind needs no restart,
// but it is not instant on the far side, and rebinding a channel TO the
// machine one is sitting at can leave two adapters live until the machine that
// held it syncs. Rebinding AWAY from the machine one is sitting at has no such
// window, which is why it is named as the clean direction.
import { useTranslation } from "react-i18next";
import { MonitorSmartphone } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ChannelStatus } from "@/lib/api/channels";
import { useMachines } from "@/lib/hooks/useMachines";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { bindingState } from "./channelBinding";
import { ChannelMachineSelect } from "./ChannelMachineSelect";

interface Props {
  name: string;
  /** The channel's current config, carried through the rebind PATCH. */
  config: Record<string, unknown>;
  /** Undefined while the status query is in flight. */
  status: ChannelStatus | undefined;
}

/** Warning class shared with the reach panel's dormant note — a configured
 *  thing that reaches nobody, said the same way wherever it is said. */
const WARNING_CLASS =
  "rounded border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

export function ChannelMachineCard({ name, config, status }: Props) {
  const { t } = useTranslation();
  const { data: machineList } = useMachines();
  const { data: syncStatus } = useSyncStatus();

  const machines = machineList?.machines ?? [];
  // The status is authoritative for the binding; the config is the fallback
  // that lets the card render before the first status lands.
  const runsOn = status?.runs_on ?? (config.runs_on as string | undefined) ?? null;
  const state = bindingState(runsOn, {
    selfId: syncStatus?.machine_id ?? null,
    known: machines.map((m) => m.machine_id),
    runsHere: status?.runs_here,
  });
  const boundName = machines.find((m) => m.machine_id === runsOn)?.name;

  /** The one line that says what is true right now. Each state gets its own
   *  sentence rather than a name plus a shrug, because the three that are not
   *  "this machine" each want a different reaction from the user. */
  const verdict = () => {
    if (state === "self") return t("channels.machine.runsHere");
    if (state === "other")
      return t("channels.machine.runsElsewhere", { machine: boundName || runsOn });
    return null;
  };

  const fault = () => {
    if (state === "unbound") return t("channels.machine.unboundBody");
    if (state === "unknown") return t("channels.machine.unknownBody", { id: runsOn });
    return null;
  };

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <MonitorSmartphone className="size-4 text-primary" aria-hidden />
          {t("channels.machine.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {verdict() ? <p className="text-sm text-foreground/80">{verdict()}</p> : null}
        {fault() ? (
          <p className={WARNING_CLASS} role="alert">
            {fault()}
          </p>
        ) : null}
        <ChannelMachineSelect
          name={name}
          config={config}
          runsOn={runsOn}
          runsHere={status?.runs_here}
        />
        <p className="max-w-prose text-xs text-muted-foreground">
          {t("channels.machine.handover")}
        </p>
        {/* The two controls on this page answer different questions and are one
            header apart; saying so here costs a line and saves a misbinding. */}
        <p className="max-w-prose text-xs text-muted-foreground">
          {t("channels.machine.notReach")}
        </p>
      </CardContent>
    </Card>
  );
}
