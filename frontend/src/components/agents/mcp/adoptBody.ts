// src/components/agents/mcp/adoptBody.ts — the request that adopts one direct MCP entry, built the one way.
//
// The adopt dialog (one entry, editable name and secret references) and the
// bulk Adopt (many entries, the defaults) send the same body: the file the
// entry sits in, a secret reference for each secret-looking key (the value
// itself never travels — the daemon moves it into the secret store), and a new
// name only when it differs.
import type { AdoptMcpEntryBody, McpEntryOut } from "@/lib/api/agents-workspace";

/** `mcp/{agent}/{entry}/{KEY}` for every secret-looking key: an address a person reads. */
export function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

export function buildAdoptBody(
  entry: McpEntryOut,
  refs: Record<string, string>,
  newName: string,
): AdoptMcpEntryBody {
  const body: AdoptMcpEntryBody = { source: entry.source };
  if (entry.secret_keys.length > 0) body.secrets = refs;
  if (newName && newName !== entry.name) body.new_name = newName;
  return body;
}
