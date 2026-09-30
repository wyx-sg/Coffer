// frontend/src/components/channel/ChannelStatusBanner.tsx
// Under the channel header: one banner for whatever is wrong (or deliberately
// quiet), saying why in plain words and what fixes it — the fix itself is the
// header's primary action. The platform's own error text, when there is one,
// follows verbatim. The daemon's diagnostics (a setting the platform will not
// honour) follow as their own banners. A healthy channel shows none.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, AlertTriangle, Info } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import type { ChannelStateKey, ChannelView } from "./channelState";
import { channelPlatform } from "./channelState";
import { useMachineName } from "./channelLabels";
import { platformLabel } from "./PlatformMark";

type Variant = "info" | "warning" | "error";

const VARIANT: Partial<Record<ChannelStateKey, Variant>> = {
  unavailable: "warning",
  unbound: "error",
  unknownMachine: "error",
  elsewhere: "info",
  off: "info",
  reconnecting: "warning",
  kicked: "error",
  sdkMissing: "error",
  connectFailed: "error",
  stopped: "error",
};

const ICON = { info: Info, warning: AlertTriangle, error: AlertCircle } as const;

interface Props {
  channel: ResourceOut;
  view: ChannelView;
  status: ChannelStatus | undefined;
  /** Why the status read failed, already translated. */
  statusError: string | null;
  /** The pairing panel, shown in a not-paired channel's banner. */
  pairing: ReactNode;
}

export function ChannelStatusBanner({ channel, view, status, statusError, pairing }: Props) {
  const { t } = useTranslation();
  const machineName = useMachineName();
  const platformKey = channelPlatform(channel.config);
  const vars = {
    platform: platformLabel(platformKey),
    machine: machineName(view.runsOn),
    id: view.runsOn ?? "",
    appId: typeof channel.config.app_id === "string" ? channel.config.app_id : "",
  };
  const variant = VARIANT[view.state];
  const Icon = variant ? ICON[variant] : null;
  const detail =
    view.state === "unavailable" ? statusError : (status?.inbound?.websocket_error ?? null);
  const diagnostics = status?.diagnostics ?? [];

  const body =
    view.state === "stopped"
      ? t(`channels.banner.stopped.body.${platformKey === "seatalk" ? "seatalk" : "telegram"}`)
      : t(`channels.banner.${view.state}.body`, vars);

  return (
    <>
      {variant && Icon ? (
        <Alert variant={variant} data-testid="channel-banner" data-state={view.state}>
          <Icon aria-hidden />
          <AlertTitle>{t(`channels.banner.${view.state}.title`, vars)}</AlertTitle>
          <AlertDescription>
            <p>{body}</p>
            {detail ? <p className="mt-1 break-words font-mono text-2xs">{detail}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}
      {view.state === "notPaired" ? (
        <Alert variant="info" data-testid="channel-banner" data-state="notPaired">
          <Info aria-hidden />
          <AlertTitle>{t("channels.banner.notPaired.title", vars)}</AlertTitle>
          <AlertDescription>
            <p>{t("channels.banner.notPaired.body")}</p>
            <div className="mt-2.5">{pairing}</div>
          </AlertDescription>
        </Alert>
      ) : null}
      {diagnostics.map((d) => (
        // A setting that reads correctly here and does nothing in the chat
        // (spec channels/telegram "Report privacy mode that defeats the group
        // configuration").
        <Alert key={d.code} variant="warning" data-testid="channel-diagnostic">
          <AlertTriangle aria-hidden />
          <AlertDescription>
            <p>{d.message}</p>
          </AlertDescription>
        </Alert>
      ))}
    </>
  );
}
