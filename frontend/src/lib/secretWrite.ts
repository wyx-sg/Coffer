// frontend/src/lib/secretWrite.ts — the one way a form stores a secret value.
//
// Registering a channel or an MCP server, editing either, all store the values
// the person typed through `POST /secrets`. That route answers 204 when the
// value is stored and 202 (with the approval) when it replaces one in use: it
// is then kept sealed and waits for a person in the Coffer app (spec secret
// "Hold a replaced value in use until a person approves it"). Callers that can
// surface that wait read the boolean; the others ignore it.
import { secretsApi } from "@/lib/api/secret";

/** Store `value` under `ref`. `true` when it now waits for approval. */
export async function writeSecret(ref: string, value: string): Promise<boolean> {
  const written = await secretsApi.set(ref, value);
  return written?.approval !== undefined && written.approval !== null;
}
