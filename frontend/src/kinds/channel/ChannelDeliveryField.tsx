// frontend/src/kinds/channel/ChannelDeliveryField.tsx
// The SeaTalk event-delivery control, shared by the add and edit dialogs. The
// platform allows one delivery method per bot, so this is a choice between two
// transports, not a pair of switches. Picking WebSocket also surfaces the two
// things Coffer cannot do for the owner: put the official SDK in place, and
// flip the method on SeaTalk's Developer Portal.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { ChannelDelivery } from "@/lib/api/channels";

const DELIVERIES: ChannelDelivery[] = ["webhook", "websocket"];

const LABEL_KEY: Record<ChannelDelivery, string> = {
  webhook: "channels.dialog.deliveryWebhook",
  websocket: "channels.dialog.deliveryWebsocket",
};

export function ChannelDeliveryField({
  delivery,
  onChange,
}: {
  delivery: ChannelDelivery;
  /** Switching transport clears the fields the other method owns. */
  onChange: (delivery: ChannelDelivery) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <Label>{t("channels.dialog.delivery")}</Label>
      <div className="flex gap-2" role="group" aria-label={t("channels.dialog.delivery")}>
        {DELIVERIES.map((d) => (
          <Button
            key={d}
            type="button"
            size="sm"
            variant={delivery === d ? "default" : "outline"}
            aria-pressed={delivery === d}
            onClick={() => onChange(d)}
          >
            {t(LABEL_KEY[d])}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t("channels.dialog.deliveryHint")}</p>
      {delivery === "websocket" ? (
        <div className="space-y-1 rounded-md border border-border bg-muted/30 p-3">
          <p className="text-xs text-muted-foreground">{t("channels.dialog.websocketSdkNote")}</p>
          <p className="text-xs text-muted-foreground">
            {t("channels.dialog.websocketPortalNote")}
          </p>
        </div>
      ) : null}
    </div>
  );
}
