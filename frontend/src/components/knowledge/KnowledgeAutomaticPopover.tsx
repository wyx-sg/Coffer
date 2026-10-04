// frontend/src/components/knowledge/KnowledgeAutomaticPopover.tsx
//
// Knowledge's "Automatic · hourly" control (design 5.1.24): curation's switch
// and interval, which Mac runs it once the vault spans several, when the last
// pass ran and the next one will, and Curate now over every collection with
// items waiting. It lives in the Knowledge header because that is what it
// upkeeps (spec internal-engine "Report and change the curation owner over
// REST and in the Knowledge popover"). While Coffer's model is not set there is nothing to curate
// with, so there is no control at all — the page shows its one muted line.
//
// "Curation runs on" follows the four-state rule of `lib/machineBinding`: an
// owner no known Mac claims is a fault (curation runs nowhere), said in place
// rather than rendered as an ordinary pick.
import { useTranslation } from "react-i18next";

import { AutomaticPopover, clockLine } from "@/components/upkeep/AutomaticPopover";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCofferModelSet,
  useInternalEngineConfig,
  useSetCurationOwner,
  useSetUpkeep,
} from "@/lib/hooks/useInternalEngine";
import { useCurateCollections, useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { bindingState, machineOptions, type MachineOption } from "@/lib/machineBinding";

/** The picker's value for "no owner named": curation runs wherever it is read. */
const NO_OWNER = "__none__";

/** Where curation runs, seen from here — null until the registry and this
 *  machine's id are known, so a healthy vault is never shown as a fault. */
function useCurationOwner(ownerId: string | null) {
  const machineQuery = useMachines();
  const self = useThisMachineId();
  if (machineQuery.isPending || self.isPending) return null;
  const machines = machineQuery.data?.machines ?? [];
  const selfId = self.machineId;
  const state = bindingState(ownerId, { selfId, known: machines.map((m) => m.machine_id) });
  return { machines, selfId, state };
}

function CurationOwnerRow({
  ownerId,
  owner,
}: {
  ownerId: string | null;
  owner: NonNullable<ReturnType<typeof useCurationOwner>>;
}) {
  const { t } = useTranslation();
  const setOwner = useSetCurationOwner();
  const { machines, selfId, state } = owner;

  // One Mac needs no choice; a stored owner nobody claims is shown even then,
  // because it means curation runs nowhere.
  if (machines.length < 2 && state !== "unknown") return null;

  const label = (o: MachineOption) =>
    !o.known
      ? t("knowledge.automatic.owner.unknown", { id: o.id })
      : o.isSelf
        ? t("knowledge.automatic.owner.thisMac", {
            name: o.name || t("knowledge.automatic.owner.thisMacFallback"),
          })
        : o.name || o.id;

  return (
    <div className="flex flex-col gap-1" data-testid="curation-owner">
      <div className="flex items-center gap-2.5">
        <span className="grow">{t("knowledge.automatic.owner.label")}</span>
        <Select
          value={ownerId ?? NO_OWNER}
          onValueChange={(v) => setOwner.mutate(v === NO_OWNER ? null : v)}
          disabled={setOwner.isPending}
        >
          <SelectTrigger
            className="h-7 w-auto max-w-[190px] gap-2 text-xs"
            aria-label={t("knowledge.automatic.owner.label")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ownerId === null ? (
              <SelectItem value={NO_OWNER}>{t("knowledge.automatic.owner.none")}</SelectItem>
            ) : null}
            {machineOptions(machines, selfId, ownerId).map((o) => (
              <SelectItem key={o.id} value={o.id}>
                {label(o)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {state === "unknown" ? (
        <span role="alert" className="text-xs leading-snug text-status-err">
          {t("knowledge.automatic.owner.fault")}
        </span>
      ) : (
        <span className="text-xs leading-snug text-text-subtle">
          {state === "unbound"
            ? t("knowledge.automatic.owner.unbound")
            : t("knowledge.automatic.owner.hint")}
        </span>
      )}
    </div>
  );
}

export function KnowledgeAutomaticPopover() {
  const { t, i18n } = useTranslation();
  const modelSet = useCofferModelSet();
  const { data: config } = useInternalEngineConfig();
  const setUpkeep = useSetUpkeep();
  const collections = useKnowledgeCollections();
  const curate = useCurateCollections();
  const ownerId = config?.curate_owner_machine_id ?? null;
  const owner = useCurationOwner(ownerId);

  const setting = config?.upkeep?.curate;
  if (modelSet !== true || !setting) return null;

  // Another Mac's timer runs the pass, so this one's last/next would be
  // someone else's schedule; say where it runs instead.
  const otherName =
    owner?.state === "other" && ownerId !== null
      ? owner.machines.find((m) => m.machine_id === ownerId)?.name || ownerId
      : null;
  const clock =
    otherName !== null
      ? t("knowledge.automatic.owner.runsElsewhere", { machine: otherName })
      : clockLine(
          t,
          i18n.language,
          setting,
          "knowledge.automatic.last",
          "knowledge.automatic.never",
        );

  const waiting = (collections.data ?? []).filter((c) => c.pending_count > 0).map((c) => c.uid);

  return (
    <AutomaticPopover
      testId="knowledge-automatic"
      title={t("knowledge.automatic.title")}
      description={t("knowledge.automatic.description")}
      setting={setting}
      busy={setUpkeep.isPending}
      onToggle={(enabled) => setUpkeep.mutate({ pass: "curate", enabled })}
      onInterval={(interval_s) => setUpkeep.mutate({ pass: "curate", interval_s })}
      pill={
        owner?.state === "unknown"
          ? { state: t("knowledge.automatic.owner.pillFault"), tone: "err" }
          : undefined
      }
      clock={clock}
      action={
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={curate.isPending || waiting.length === 0}
          onClick={() => curate.mutate(waiting)}
        >
          {curate.isPending ? t("knowledge.automatic.curating") : t("knowledge.curate.now")}
        </Button>
      }
    >
      {owner ? <CurationOwnerRow ownerId={ownerId} owner={owner} /> : null}
    </AutomaticPopover>
  );
}
