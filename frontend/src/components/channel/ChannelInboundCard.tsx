// frontend/src/components/channel/ChannelInboundCard.tsx
// SeaTalk-only detail card: the channel's inbound state. A SeaTalk channel
// receives every event over one outbound websocket connection Coffer holds to
// the platform, so the card reports that connection's state and, when there is
// one, the last error verbatim (spec channels/seatalk "Report the websocket
// connection as the channel's inbound state"). There is no URL to register, no
// listener, port or tunnel, and nothing to probe: the connection state is the
// health answer.
import { useTranslation } from "react-i18next";
import { PlugZap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { InboundInfo, WebSocketState } from "@/lib/api/channels";
import { toneClass, type Tone } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { StatusRow } from "./ChannelDetailCards";

/** A live socket is the only healthy state; a failed one is an error. */
function stateTone(state: WebSocketState | null): Tone {
  if (state === "connected") return "ok";
  if (state === "kicked" || state === "sdk_missing" || state === "error") return "error";
  return "warn";
}

export function ChannelInboundCard({ inbound }: { inbound: InboundInfo }) {
  const { t } = useTranslation();
  const state = inbound.websocket_state;

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <PlugZap className="size-4 text-primary" aria-hidden />
          {t("channels.inbound.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <StatusRow
          label={t("channels.inbound.connection")}
          value={
            <Badge
              variant="outline"
              className={cn("border-transparent", toneClass(stateTone(state)))}
            >
              {t(`channels.inbound.state.${state ?? "unknown"}`)}
            </Badge>
          }
        />
        {inbound.websocket_error ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
          >
            {inbound.websocket_error}
          </p>
        ) : null}
        <p className="pt-1 text-xs text-muted-foreground">{t("channels.inbound.hint")}</p>
      </CardContent>
    </Card>
  );
}
