// src/components/mcp/server/secretRows.ts — which stored secret a server's callout acts on.
import type { SecretRef } from "@/lib/api/secret";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";

/** The secret missing on this Mac, and the key its env or headers cite (for Replace key). */
export function serverSecretRows(
  refs: readonly SecretRef[] | undefined,
  detail: McpStatusDetail | null | undefined,
): { missing: SecretRef | null; key: SecretRef | null } {
  const rowOf = (ref: string | null | undefined) => refs?.find((r) => r.ref === ref) ?? null;
  // A key typed into the config itself has no secret to replace: null, and the
  // caller opens the edit dialog instead.
  const key = detail?.requires?.find((r) => r.kind === "secret" && r.secret)?.secret;
  return {
    missing: rowOf(detail?.missing_secret_ref),
    key: key ? rowOf(key.startsWith("secret/") ? key : `secret/${key}`) : null,
  };
}
