// frontend/src/components/channel/ChannelMachineSelect.tsx
// The control that says — and changes — which machine runs a channel's
// adapter (spec channels, "Bind each channel to the one machine that runs it"). One component for both
// surfaces: the list row's cell and the detail page's status strip, so the
// two can never offer different machines or write the binding differently.
//
// It is deliberately NOT the reach control next to it. Reach asks which agents
// this channel may drive; this asks which machine answers the bot at all, and
// a channel needs both answers to be live. They sit in different columns, use
// different vocabulary, and share no field.
//
// What a rebind costs, and that this is not reach, is owed to the reader by
// the spec but is not something to read on every visit, so it lives in
// MachineBindingHelp — a "?" beside whichever label names the picker — rather
// than in prose under it.
//
// Colour comes from the shared statusColors vocabulary rather than a local
// choice, because two of the four states are faults and must read as faults
// wherever they appear: `unknown` (bound to a machine nobody claims — the
// channel runs NOWHERE and only a rebind fixes it) is the error tone, and
// `unbound` is the warning tone. A machine that is simply someone else's is
// not a problem and is not tinted.
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRebindChannel } from "@/lib/hooks/useChannels";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { machineOptions, type MachineOption } from "@/lib/machineBinding";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { bindingState } from "./channelBinding";

interface Props {
  /** The channel being bound — its identity, which the PATCH is addressed to. */
  uid: string;
  /** Its label, for the picker's accessible name and the toast. */
  name: string;
  /** Its current config — carried through the PATCH untouched beside the new
   *  binding, so a rebind never drops a secret ref. */
  config: Record<string, unknown>;
  /** The stored binding; null is unbound. */
  runsOn: string | null;
  /** `ChannelStatus.runs_here` where a status has been fetched. Passed rather
   *  than derived: it is the daemon's own answer to the same question. */
  runsHere?: boolean;
  /** Shrinks the trigger to table-row height. */
  compact?: boolean;
}

export function ChannelMachineSelect({
  uid,
  name,
  config,
  runsOn,
  runsHere,
  compact = false,
}: Props) {
  const { t } = useTranslation();
  const { data: machineList } = useMachines();
  const { machineId: selfId } = useThisMachineId();
  const rebind = useRebindChannel(uid, name);

  const machines = machineList?.machines ?? [];
  const options = machineOptions(machines, selfId, runsOn);
  const state = bindingState(runsOn, {
    selfId,
    known: machines.map((m) => m.machine_id),
    runsHere,
  });

  /** A machine as the user should read it: its registry name, the raw id when
   *  the registry has none, and an explicit marking for the two states that
   *  need one — this machine, and an id nobody claims. */
  const labelFor = (option: MachineOption) => {
    if (!option.known) return t("channels.machine.unknown", { id: option.id });
    const label = option.name || (option.isSelf ? t("channels.machine.thisMachine") : option.id);
    return option.isSelf ? t("channels.machine.self", { name: label }) : label;
  };

  const tone =
    state === "unknown" ? toneClass("error") : state === "unbound" ? toneClass("warn") : undefined;

  return (
    <Select
      // Unbound is the empty value on purpose. Radix shows the PLACEHOLDER for
      // it, which is how "bound to nobody" gets reported without becoming a
      // choice: binding a channel to nobody is asking for one that runs
      // nowhere, and no surface should offer that as a step.
      value={runsOn ?? ""}
      disabled={rebind.isPending}
      onValueChange={(next) => {
        if (next === "" || next === runsOn) return;
        const picked = options.find((o) => o.id === next);
        rebind.mutate({ config, runsOn: next, machine: picked ? labelFor(picked) : next });
      }}
    >
      <SelectTrigger
        aria-label={t("channels.machine.pickerLabel", { name })}
        data-testid="channel-machine-select"
        className={cn(compact && "h-7 w-auto min-w-[9rem] text-xs", tone)}
      >
        <SelectValue placeholder={t("channels.machine.unbound")} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.id} value={option.id}>
            {labelFor(option)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * The explanation every surface that offers a rebind owes (spec channels,
 * "Bind each channel to the one machine that runs it"): a rebind needs no
 * restart but is not instant on the far side — binding a channel to this
 * machine while another still holds it leaves both answering until that
 * machine's next round — and this control is not reach, which the header
 * sets a row away. Placed beside the picker's label rather than in its menu,
 * so it can be read before the choice rather than only while making it.
 */
export function MachineBindingHelp() {
  const { t } = useTranslation();
  return (
    <HelpTip label={t("channels.machine.helpLabel")}>
      <p>{t("channels.machine.handover")}</p>
      <p>{t("channels.machine.notReach")}</p>
    </HelpTip>
  );
}
