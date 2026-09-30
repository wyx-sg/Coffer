// frontend/src/components/channel/ChannelListRow.tsx
// One row of the Channels list: the platform mark, "SeaTalk · Team bot", the
// line that says what state it is in (in its status colour when something is
// wrong), and the status dot on the right.
import { Link } from "react-router-dom";

import { StatusDot } from "@/components/status/StatusDot";
import type { ResourceOut } from "@/lib/api/resources";
import { toneTextClass } from "@/lib/statusColors";
import { STATUS_TONE } from "@/components/status/statusTone";
import { cn } from "@/lib/utils";
import { channelHeading, useChannelStateWords } from "./channelLabels";
import type { ChannelView } from "./channelState";
import { channelPlatform } from "./channelState";
import { PlatformMark } from "./PlatformMark";

interface Props {
  channel: ResourceOut;
  view: ChannelView;
  to: string;
  current: boolean;
}

export function ChannelListRow({ channel, view, to, current }: Props) {
  const words = useChannelStateWords();
  const { line } = words(view);
  return (
    <li>
      <Link
        to={to}
        aria-current={current ? "page" : undefined}
        data-testid="channel-row"
        data-state={view.state}
        className={cn(
          "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-text transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          current ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <PlatformMark platform={channelPlatform(channel.config)} size="md" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm font-label">{channelHeading(channel)}</span>
          <span className={cn("truncate text-xs", toneTextClass(STATUS_TONE[view.tone]))}>
            {line}
          </span>
        </span>
        <StatusDot tone={view.tone} />
      </Link>
    </li>
  );
}
