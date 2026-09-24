// frontend/src/components/settings/CurationOwner.tsx
//
// Which machine runs curation (spec knowledge), on the curate row of Settings
// → Engine → Automatic upkeep.
//
// Curation rewrites the derived documents unattended. Once a vault spans
// machines, exactly one may run it: two machines folding the same sources into
// two differently-named documents is a merge git resolves perfectly — two
// additions at two paths — and a vault that then holds the same knowledge
// twice. So the settings document names one owner, and it travels with the
// document to every machine.
//
// That owner is the same shape as a channel's binding and reuses the same
// rules (`@/lib/machineBinding`), but NOT the same consequences, and the
// difference is the reason this file exists rather than a shared card:
//
//   • unowned. A channel bound to nobody runs nowhere — fail closed, because
//     answering a platform twice cannot be walked back. Curation owned by
//     nobody runs HERE: a vault that never named an owner is a vault with one
//     machine, and being wrong costs a duplicated document, not a bot
//     answering itself. So `unbound` reads as a note, not a fault.
//   • unknown. The owner names a machine the registry no longer claims —
//     retired, or never converged under that id. Curation then runs on NO
//     machine, on every machine, silently: the switch above still reads On,
//     the interval still reads every six hours, and nothing else in the
//     product says otherwise. That is the one state here that is a fault, and
//     the reason this row is on the page at all.
//
// The two actions are deliberately the only two: claim it for the machine you
// are sitting at, and clear it. Naming a machine you are not at would need the
// registry to be right about a machine you cannot see, which is exactly the
// assumption the `unknown` state is the wreck of.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSetCurationOwner } from "@/lib/hooks/useInternalEngine";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { bindingState, machineOptionFor } from "@/lib/machineBinding";
import { cn } from "@/lib/utils";

interface Props {
  /** `InternalEngineConfigOut.curate_owner_machine_id` — null on a vault that
   *  has never named an owner, which curates wherever it is read. */
  ownerId: string | null;
}

export function CurationOwner({ ownerId }: Props) {
  const { t } = useTranslation();
  const machineQuery = useMachines();
  const self = useThisMachineId();
  const setOwner = useSetCurationOwner();
  const [confirmClear, setConfirmClear] = useState(false);

  // The gate is load-bearing, not politeness. Before the registry lands,
  // `known` is empty and every owner id in the world looks like a machine
  // nobody claims — this row would accuse a perfectly healthy vault of the one
  // fault it exists to report, every time the page opens.
  if (machineQuery.isPending || self.isPending) {
    return <Skeleton className="mt-2 h-16 w-full" />;
  }

  const machines = machineQuery.data?.machines ?? [];
  const selfId = self.machineId;
  const state = bindingState(ownerId, {
    selfId,
    known: machines.map((m) => m.machine_id),
  });

  // A machine as the user should read it: the registry's name, "this machine"
  // when it is this one and the registry has no name for it (a vault that has
  // never converged has no registry at all), and the raw id only when there is
  // genuinely nothing else to say.
  const option = ownerId === null ? null : machineOptionFor(machines, selfId, ownerId);
  const ownerName =
    option === null
      ? ""
      : option.name || (option.isSelf ? t("settings.upkeep.owner.thisMachine") : option.id);

  const runsOn =
    state === "unbound"
      ? t("settings.upkeep.owner.everyMachine")
      : state === "unknown"
        ? t("settings.upkeep.owner.unknownMachine", { id: ownerId })
        : ownerName;

  const explanation =
    state === "self"
      ? t("settings.upkeep.owner.self")
      : state === "other"
        ? t("settings.upkeep.owner.other", { machine: ownerName })
        : state === "unbound"
          ? t("settings.upkeep.owner.unowned")
          : t("settings.upkeep.owner.fault", { id: ownerId });

  const fault = state === "unknown";

  return (
    <div
      data-testid="curation-owner"
      className={cn(
        "mt-3 space-y-2 rounded-md border px-3 py-2",
        fault ? "border-destructive/40 bg-destructive/10" : "border-border bg-muted/30",
      )}
    >
      <p className="text-xs">
        <span className="text-muted-foreground">{t("settings.upkeep.owner.label")} </span>
        <span className={cn("font-medium", fault && "text-destructive")}>{runsOn}</span>
      </p>
      <p
        // Only the fault interrupts a reader: the other three are the answer to
        // a question the row was opened to ask.
        role={fault ? "alert" : undefined}
        className={cn("text-xs", fault ? "text-destructive" : "text-muted-foreground")}
      >
        {explanation}
      </p>
      <div className="flex flex-wrap gap-2">
        {state === "self" ? null : (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* A span so the tooltip still opens on a disabled button — a
                  disabled control with no reason given is the whole complaint
                  this row is fixing. */}
              <span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={selfId === null || setOwner.isPending}
                  onClick={() => selfId !== null && setOwner.mutate(selfId)}
                >
                  {t("settings.upkeep.owner.takeOver")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-[18rem]">
              {selfId === null
                ? t("settings.upkeep.owner.noMachineId")
                : t("settings.upkeep.owner.takeOverHint")}
            </TooltipContent>
          </Tooltip>
        )}
        {ownerId === null ? null : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={setOwner.isPending}
            onClick={() => setConfirmClear(true)}
          >
            {t("settings.upkeep.owner.clear")}
          </Button>
        )}
      </div>

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title={t("settings.upkeep.owner.clearTitle")}
        description={t("settings.upkeep.owner.clearBody")}
        confirmLabel={t("settings.upkeep.owner.clear")}
        pending={setOwner.isPending}
        error={setOwner.error}
        // The caller-closes form: the dialog shuts in `onSuccess` and nowhere
        // else, so a refused clear stays open with its reason instead of
        // vanishing as though it had gone through.
        onConfirm={() => setOwner.mutate(null, { onSuccess: () => setConfirmClear(false) })}
      />
    </div>
  );
}
