// src/components/reach/ReachButton.tsx — ReachControl's one trigger: the current reach as its label, with the chosen agents' badges.
//
// Foundations-Reach "Button": h26, a secondary look, 12/550, a 12px chevron.
// The label IS the reach and stays the button's whole accessible name — the
// badges and the Disabled dot beside it are decoration (aria-hidden), because
// the words already say what they show. "Every agent" shows no badges (it is a
// rule, not a list); a restricted reach shows one sm badge per chosen agent, in
// Agents-page order; Disabled shows a neutral dot before the word.
//
// A plain <button>, not ui/Button: that one resizes every descendant svg, which
// would redraw the agent marks at chevron size.
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import type { ReachMode } from "@/components/reach/reachState";
import { cn } from "@/lib/utils";

interface ReachBadgeAgent {
  uid: string;
  type: string;
  name: string;
}

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  /** The live reach; `null` for the bulk bar, which names an action instead. */
  live: ReachMode | null;
  label: string;
  /** The chosen agents, drawn as badges only while the reach is restricted. */
  chosen: ReachBadgeAgent[];
  /** Colours the button: this resource reaches nobody here. */
  warn?: boolean;
}

export const ReachButton = forwardRef<HTMLButtonElement, Props>(function ReachButton(
  { live, label, chosen, warn = false, className, type = "button", ...props },
  ref,
) {
  const badges = live === "restricted" ? sortAgents(chosen) : [];
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex h-control-sm items-center whitespace-nowrap rounded-md border border-border bg-surface-raised pl-[5px] pr-1.5 text-xs font-label text-text",
        "transition-colors duration-fast ease-standard hover:bg-surface-hover active:bg-surface-selected",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        "disabled:pointer-events-none disabled:opacity-disabled",
        warn && "text-warning",
        className,
      )}
      {...props}
    >
      {badges.length > 0 ? (
        <span aria-hidden className="mr-2 inline-flex items-center gap-[3px]">
          {badges.map((agent) => (
            <AgentBadge
              key={agent.uid}
              type={agent.type}
              name={agent.name}
              size="sm"
              tooltip={false}
            />
          ))}
        </span>
      ) : null}
      {live === "disabled" ? (
        <span aria-hidden className="mr-1.5 size-[7px] shrink-0 rounded-full bg-neutral" />
      ) : null}
      <span className="px-px">{label}</span>
      <ChevronDown aria-hidden className="ml-1 size-3 shrink-0 text-text-subtle" />
    </button>
  );
});
