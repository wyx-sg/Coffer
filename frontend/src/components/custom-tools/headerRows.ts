// src/components/custom-tools/headerRows.ts — a group's header rows between the wire (`headers`: a plain value or a
// Secrets-page name that holds the WHOLE value) and the shared header-row form (`KeyValueSecretRow`).
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import type { CustomToolGroup, CustomToolHeaderIn } from "@/lib/api/customTools";

/** The rows an edit form starts from. */
export function headerRowsOf(group: Pick<CustomToolGroup, "headers">): KeyValueSecretRow[] {
  return group.headers.map((h) =>
    h.secret
      ? { key: h.name, value: { kind: "stored", name: h.secret } }
      : { key: h.name, value: { kind: "plain", value: h.value ?? "" } },
  );
}

/** What a save sends: rows with a name, a secret by its name or a plain value. Call
 *  `persistNewSecrets` on the rows' values first. */
export function headersIn(rows: readonly KeyValueSecretRow[]): CustomToolHeaderIn[] {
  return rows
    .filter((r) => r.key.trim() !== "")
    .map((r) =>
      r.value.kind === "plain"
        ? { name: r.key.trim(), value: r.value.value }
        : { name: r.key.trim(), secret: r.value.name },
    );
}

/** The Secrets-page names a group's headers read from. */
export function groupSecrets(group: Pick<CustomToolGroup, "headers">): string[] {
  return group.headers.flatMap((h) => (h.secret ? [h.secret] : []));
}

/** The first of them — what a banner or a row names. */
export function firstSecret(group: Pick<CustomToolGroup, "headers">): string {
  return groupSecrets(group)[0] ?? "";
}

/** The secret a banner or a row names for `state`: the first header in that state (a
 *  pending approval is named by the group's `pending_secrets`), else the first secret. */
export function secretInState(
  group: Pick<CustomToolGroup, "headers" | "pending_secrets">,
  state: "missing" | "pending_approval",
): string {
  if (state === "pending_approval" && group.pending_secrets[0]) return group.pending_secrets[0];
  return group.headers.find((h) => h.secret_state === state)?.secret ?? firstSecret(group);
}
