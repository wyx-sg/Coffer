// src/components/agent/AgentOption.tsx — an agent inside a control: its mark and its display name.
//
// The one form every select item, checklist row and trigger value uses, so an
// agent reads the same in a dropdown as on the Agents page. The name is the
// product name (`Claude Code`), never the registry key (`claude-code`); the
// stored value stays the uid or key and is the caller's business.
import { AgentBadge } from "./AgentBadge";

interface Props {
  /** Agent type key; empty or unknown draws the neutral mark. */
  type: string;
  name: string;
}

export function AgentOption({ type, name }: Props) {
  return <AgentBadge type={type} name={name} size="sm" showName tooltip={false} />;
}
