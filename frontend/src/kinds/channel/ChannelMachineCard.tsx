// frontend/src/kinds/channel/ChannelMachineCard.tsx
//
// Runtime affinity (spec 010 / ADR-043): a synced channel runs on exactly ONE
// machine. This card shows which machine that is — or that the channel is
// unbound and running nowhere — and offers a one-click rebind to this machine
// (the change reaches the other machine on the next sync round trip).
import { Laptop } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useUpdateChannel } from "@/lib/hooks/useChannels";
import { useSyncMachines } from "@/lib/hooks/useSync";

import { StatusRow } from "./ChannelDetailCards";

export function ChannelMachineCard({
  name,
  config,
}: {
  name: string;
  config: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const { data } = useSyncMachines();
  const update = useUpdateChannel();
  const machines = data?.machines ?? [];
  const runsOn = typeof config.runs_on === "string" && config.runs_on ? config.runs_on : null;
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
            onClick={() =>
              update.mutate({
                name,
                config: { ...config, runs_on: local.machine_id },
                secrets: [],
              })
            }
          >
            {t("channels.machine.runHere")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
