// src/lib/overview/kinds.ts — how the Overview names a kind: its label key, its icon, and whether its name is an identifier.
//
// One table for the "Needs you" rows, the source-error lines and the Recent
// activity rows, so a kind reads the same wherever the page mentions it. An
// MCP server's and a skill's name is fixed once registered, so it is shown in
// mono as an identifier; every other kind's name is prose.
import {
  Bot,
  Boxes,
  Brain,
  CircleDot,
  Library,
  Radio,
  RefreshCw,
  Server,
  Sparkles,
  SquareTerminal,
  Workflow,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export interface KindMeta {
  /** i18n key of the kind's singular label ("MCP server"). */
  labelKey: string;
  icon: LucideIcon;
  /** The kind's name is a fixed identifier, shown in mono. */
  identifier: boolean;
}

const KINDS: Record<string, KindMeta> = {
  agent: { labelKey: "overview.kinds.agent", icon: Bot, identifier: false },
  provider: { labelKey: "overview.kinds.provider", icon: Boxes, identifier: false },
  mcp_server: { labelKey: "overview.kinds.mcp_server", icon: Server, identifier: true },
  skill: { labelKey: "overview.kinds.skill", icon: Sparkles, identifier: true },
  channel: { labelKey: "overview.kinds.channel", icon: Radio, identifier: false },
  knowledge: { labelKey: "overview.kinds.knowledge", icon: Library, identifier: false },
  memory: { labelKey: "overview.kinds.memory", icon: Brain, identifier: false },
  sync: { labelKey: "overview.kinds.sync", icon: RefreshCw, identifier: false },
  reconcile: { labelKey: "overview.kinds.reconcile", icon: Workflow, identifier: false },
  cli: { labelKey: "overview.kinds.cli", icon: SquareTerminal, identifier: true },
  custom_tool: { labelKey: "overview.kinds.custom_tool", icon: Wrench, identifier: true },
};

const OTHER: KindMeta = { labelKey: "overview.kinds.other", icon: CircleDot, identifier: false };

/** The kind's label, icon and name style; a kind this table does not know reads "Other". */
export function kindMeta(kind: string | null | undefined): KindMeta {
  return (kind && KINDS[kind]) || OTHER;
}
