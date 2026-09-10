// frontend/src/lib/api/agents-workspace.ts — wire types for the agent workspace
// surfaces (MCP entries, unmanaged skills). Split out of agents.ts for
// the file-size budget; re-exported there so existing import paths keep working.

export interface McpEntryOut {
  name: string;
  source: string;
  transport: "stdio" | "http";
  command: string | null;
  args: string[];
  env_keys: string[];
  secret_keys: string[];
  url: string | null;
  header_keys: string[];
  enabled: boolean | null;
  is_coffer: boolean;
  matches_resource: string | null;
}

export interface McpEntriesResponse {
  items: McpEntryOut[];
  parse_errors: { source: string; path: string; error: string }[];
}

export interface AdoptMcpEntryBody {
  source?: string;
  new_name?: string;
  secrets?: Record<string, string>;
}

export interface UnmanagedSkillOut {
  name: string;
  path: string;
  location: string;
  valid: boolean;
  reason: string | null;
  foreign_link: boolean;
}

export interface UnmanagedSkillsResponse {
  items: UnmanagedSkillOut[];
}
