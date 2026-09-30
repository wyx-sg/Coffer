// src/components/agent/AgentBadge.tsx — how an agent is shown anywhere: its official mark on a neutral tile.
//
// Every agent sits on the same `bg-chip` tile so colour outside the mark stays
// reserved for state: a connected agent is plain, and only a problem adds a
// mark — a warning corner dot (not connected), a dashed empty tile (not
// installed) or a faded neutral fill (disabled). The name is never hidden: a
// badge without a visible name carries it, with its state, in the aria-label
// and the tooltip (Foundations-AgentBadge, spec web-ui "Show an agent by its
// official mark").
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { agentTypeLabel } from "@/lib/agents/display";
import { cn } from "@/lib/utils";
import { AgentMark } from "./AgentMark";
import { agentMarkKind } from "./agentMarkKind";

export type AgentBadgeState = "connected" | "not-connected" | "not-installed" | "disabled";
type AgentBadgeSize = "sm" | "md" | "lg";

interface AgentBadgeProps {
  /** Agent type key: "claude_code" | "codex" | anything else → neutral glyph. */
  type: string;
  /** Display name; defaults to agentTypeLabel(type). */
  name?: string;
  size?: AgentBadgeSize;
  state?: AgentBadgeState;
  /** Show the name beside the tile. */
  showName?: boolean;
  /** Tooltip "name · state" on hover (default true). */
  tooltip?: boolean;
  className?: string;
}

const SIZE: Record<AgentBadgeSize, { tile: string; gap: string; mark: number; blossom: number }> = {
  sm: { tile: "h-[18px] w-[22px] rounded-sm", gap: "gap-1.5", mark: 11, blossom: 20 },
  md: { tile: "size-6 rounded-item", gap: "gap-2", mark: 14, blossom: 26 },
  lg: { tile: "size-8 rounded-lg", gap: "gap-2.5", mark: 18, blossom: 35 },
};

export function AgentBadge({
  type,
  name,
  size = "md",
  state,
  showName = false,
  tooltip = true,
  className,
}: AgentBadgeProps) {
  const { t } = useTranslation();
  const label = name ?? agentTypeLabel(type);
  const geo = SIZE[size];
  // Connected is the quiet default: only a problem is spoken.
  const problem = state && state !== "connected" ? state : undefined;
  const ariaLabel = problem
    ? t("agentBadge.label", { name: label, state: t(`agentBadge.stateInline.${problem}`) })
    : label;
  const tip = state
    ? t("agentBadge.tooltip", { name: label, state: t(`agentBadge.state.${state}`) })
    : label;

  const tile = (
    <span
      className={cn("relative inline-flex shrink-0", state === "disabled" && "opacity-disabled")}
    >
      <span
        data-agent-mark={agentMarkKind(type)}
        className={cn(
          "inline-flex items-center justify-center overflow-hidden border text-text-muted",
          geo.tile,
          state === "not-installed"
            ? "border-dashed border-text-subtle bg-transparent"
            : state === "disabled"
              ? "border-transparent bg-neutral-soft"
              : "border-transparent bg-chip",
        )}
      >
        <AgentMark type={type} markSize={geo.mark} blossomSize={geo.blossom} />
      </span>
      {state === "not-connected" ? (
        <span
          aria-hidden
          className="absolute -bottom-[3px] -right-[3px] size-[7px] rounded-full bg-warning ring-2 ring-surface"
        />
      ) : null}
    </span>
  );

  const badge = (
    <span
      role="img"
      aria-label={ariaLabel}
      className={cn("inline-flex min-w-0 items-center", geo.gap, className)}
    >
      {tile}
      {showName ? (
        <span
          aria-hidden
          className={cn(
            "min-w-0 truncate text-sm font-normal",
            state === "not-installed" ? "text-text-muted" : "text-text",
          )}
        >
          {label}
        </span>
      ) : null}
    </span>
  );

  if (!tooltip) return badge;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent>{tip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
