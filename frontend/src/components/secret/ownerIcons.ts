// src/components/secret/ownerIcons.ts — the icon each kind of secret owner wears in the by-owner view.
import {
  Cpu,
  KeyRound,
  MessageSquare,
  RefreshCw,
  Server,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { OwnerKind } from "@/lib/secrets/listState";

export const OWNER_ICONS: Record<OwnerKind, LucideIcon> = {
  mcp_server: Server,
  channel: MessageSquare,
  provider: Cpu,
  sync: RefreshCw,
  custom_tool: Wrench,
  other: KeyRound,
};
