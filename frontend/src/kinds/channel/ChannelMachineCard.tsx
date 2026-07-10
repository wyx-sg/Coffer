// frontend/src/kinds/channel/ChannelMachineCard.tsx
//
// Runtime affinity (ADR-045 framework scope, amending spec 010 / ADR-043): a
// synced channel runs on exactly ONE machine. This card shows which machine
// that is — or that the channel is unbound (dormant scope, `{}`) and running
// nowhere — and offers a one-click rebind to this machine via the scope
// endpoints (the change reaches the other machine on the next sync round
// trip). Reads/writes the resource's `scope` (Task 7's
// GET/PUT /resources/channel/{name}/scope), NOT `config.runs_on`, which is
// deprecated/inert — see coffer.domain.channel.config.
import { Laptop } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useChannelScope, useUpdateChannelScope } from "@/lib/hooks/useChannels";
import { useSyncMachines } from "@/lib/hooks/useSync";

import { StatusRow } from "./ChannelDetailCards";

export function ChannelMachineCard({ name }: { name: string }) {
  const { t } = useTranslation();
  const { data: machinesData } = useSyncMachines();
  const { data: scopeData } = useChannelScope(name);
  const update = useUpdateChannelScope(name);
  const machines = machinesData?.machines ?? [];
  // Channels use only the "machine" axis: at most one key, always "*" — the
  // single bound machine id, or none (dormant, `{}`).
  const runsOn = scopeData?.scope ? (Object.keys(scopeData.scope)[0] ?? null) : null;
  const bound = machines.find((m) => m.machine_id === runsOn);
  const local = machines.find((m) => m.is_local);
  const runsHere = runsOn !== null && bound?.is_local === true;

  const label =
    runsOn === null ? (
      <span className="text-amber-600">{t("channels.machine.unbound")}</span>
    ) : runsHere ? (
      <Badge>{t("channels.machine.thisMachine")}</Badge>
    ) : (
      <Badge variant="outline">{bound?.display_name ?? runsOn}</Badge>
    );

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Laptop className="size-4 text-primary" aria-hidden />
          {t("channels.machine.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <StatusRow label={t("channels.machine.runsOn")} value={label} />
        <p className="text-xs text-muted-foreground">{t("channels.machine.hint")}</p>
        {!runsHere && local && (
          <Button
            size="sm"
            variant="secondary"
            disabled={update.isPending}
            onClick={() => update.mutate({ [local.machine_id]: "*" })}
          >
            {t("channels.machine.runHere")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
