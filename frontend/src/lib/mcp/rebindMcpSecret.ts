// src/lib/mcp/rebindMcpSecret.ts — point one env var / header of an MCP server at another stored secret.
//
// The saved config is the stored one with `transport.secret_refs[field]` replaced; every other key is kept.
import { withInlineApproval } from "@/lib/inlineApproval";
import { resourcesApi, type ResourceOut } from "@/lib/api/resources";

export async function rebindMcpSecret(
  resource: Pick<ResourceOut, "uid" | "config">,
  field: string,
  ref: string,
): Promise<void> {
  const config = JSON.parse(JSON.stringify(resource.config ?? {})) as Record<string, unknown>;
  const transport = { ...((config.transport as Record<string, unknown> | undefined) ?? {}) };
  transport.secret_refs = {
    ...((transport.secret_refs as Record<string, string> | undefined) ?? {}),
    [field]: ref,
  };
  await withInlineApproval(
    () => resourcesApi.update(resource.uid, { config: { ...config, transport } }),
    () => resource.uid,
  );
}
