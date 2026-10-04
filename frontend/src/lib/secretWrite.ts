// frontend/src/lib/secretWrite.ts — the one way a form stores a secret value.
//
// Registering a channel or an MCP server, editing either, all store the values
// the person typed through `POST /secrets`, which stores the value at once
// (204).
import { secretsApi } from "@/lib/api/secret";

/** Store `value` under `ref`. */
export async function writeSecret(ref: string, value: string): Promise<void> {
  await secretsApi.set(ref, value);
}
