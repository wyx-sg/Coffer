// frontend/src/components/channel/ChannelRowCells.tsx
// The channels list's per-row cells.
//
// They live apart from ChannelsTable because they are the half that FETCHES:
// each of these cells mounts the row's own `/channels/{uid}/status` query (one
// request per row, shared by all three through the query cache) while the table
// itself is a pure arrangement of columns over the list payload it was handed.
// Splitting on that seam keeps "what a row shows" readable without scrolling
// past "how a row learns it" — and it is why the pure config readers stayed
// behind with the columns that call them: nothing here reads a row's config
// except for the one field the machine picker needs.
import { useTranslation } from "react-i18next";

import { ChannelMachineSelect } from "@/components/channel/ChannelMachineSelect";
import { Badge } from "@/components/ui/badge";
import { useChannelStatus } from "@/lib/hooks/useChannels";
import { cn } from "@/lib/utils";
import { channelHealthClass } from "./channelHealth";
import type { ResourceOut } from "@/lib/api/resources";

/**
 * Live runtime health cell — the adapter `running` state from the same cached
 * /channels/{uid}/status query the PairedCell uses. Mirrors the MCP-server
 * surface's ServerHealthCell/HealthBadge: an outline Badge on the shared
 * status tokens, through the one running/stopped tone mapping the detail
 * page's Status card uses too (running -> ok, stopped -> warn).
 */
export function HealthCell({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const { data: status } = useChannelStatus(uid);
  if (!status) return <span className="text-muted-foreground">{t("common.emptyValue")}</span>;
  return (
    <Badge
      variant="outline"
      className={cn("whitespace-nowrap border-transparent", channelHealthClass(status.running))}
      data-testid="channel-health-badge"
    >
      {status.running ? t("channels.status.running") : t("channels.status.stopped")}
    </Badge>
  );
}

/** Live "Paired · <name>" / "Not paired" cell — one status query per row. */
export function PairedCell({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const { data: status } = useChannelStatus(uid);
  if (!status) return <span className="text-muted-foreground">{t("common.emptyValue")}</span>;
  if (status.peer === null) {
    return <span className="text-muted-foreground">{t("channels.notPaired")}</span>;
  }
  return (
    <span className="text-foreground">
      {t("channels.paired")} · {status.peer.display_name}
    </span>
  );
}

/**
 * Which machine runs this channel's adapter, and the picker that moves it.
 *
 * The binding rides the row's own config, so the cell costs no extra request
 * for the id; `runs_here` comes off the status query the row already mounts,
 * because whether the bound machine is THIS one is the daemon's answer to give
 * and not a comparison this table should be making on its own.
 */
export function MachineCell({ row }: { row: ResourceOut }) {
  const { data: status } = useChannelStatus(row.uid);
  const configured = row.config.runs_on;
  return (
    <ChannelMachineSelect
      uid={row.uid}
      name={row.name}
      config={row.config}
      runsOn={status?.runs_on ?? (typeof configured === "string" && configured ? configured : null)}
      runsHere={status?.runs_here}
      compact
    />
  );
}
