// src/components/custom-tools/headerRows.ts — a group's header rows between the wire (`headers`: a plain value or a
// Secrets-page name that holds the WHOLE value) and the shared header-row form (`KeyValueSecretRow`).
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import { schemeOfRow } from "@/lib/authScheme";
import type {
  CustomToolEnvironment,
  CustomToolGroup,
  CustomToolHeaderIn,
  CustomToolHeaderOut,
} from "@/lib/api/customTools";

/** Anything that holds header rows: a group (its first environment's) or one environment. */
type WithHeaders = { headers: readonly CustomToolHeaderOut[] };

/** Every header row of every environment of a group. */
function allHeaders(group: Pick<CustomToolGroup, "headers" | "environments">) {
  return group.environments?.length
    ? group.environments.flatMap((e: CustomToolEnvironment) => e.headers)
    : group.headers;
}

/** The rows an edit form starts from. */
export function headerRowsOf(group: WithHeaders): KeyValueSecretRow[] {
  return group.headers.map((h) =>
    h.secret
      ? { key: h.name, value: { kind: "stored", name: h.secret }, scheme: h.scheme }
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
        : { name: r.key.trim(), secret: r.value.name, scheme: schemeOfRow(r) },
    );
}

/** The Secrets-page names a group's headers read from, in every environment. */
export function groupSecrets(group: Pick<CustomToolGroup, "headers" | "environments">): string[] {
  return allHeaders(group).flatMap((h) => (h.secret ? [h.secret] : []));
}

/** The first of them — what a banner or a row names. */
export function firstSecret(group: Pick<CustomToolGroup, "headers" | "environments">): string {
  return groupSecrets(group)[0] ?? "";
}

/** The secret a banner or a row names for `state`: the first header in that state (a
 *  pending or refused approval is named by the group's `pending_secrets` or
 *  `rejected_secrets`), else the first secret. */
export function secretInState(
  group: Pick<CustomToolGroup, "headers" | "environments" | "pending_secrets"> &
    Partial<Pick<CustomToolGroup, "rejected_secrets">>,
  state: "missing" | "pending_approval" | "rejected",
): string {
  if (state === "pending_approval" && group.pending_secrets[0]) return group.pending_secrets[0];
  if (state === "rejected" && group.rejected_secrets?.[0]) return group.rejected_secrets[0];
  return allHeaders(group).find((h) => h.secret_state === state)?.secret ?? firstSecret(group);
}

/** The group's headers as a save sends them, with `header` reading from the secret `id` instead. */
export function headersWithSecret(
  group: WithHeaders,
  header: string,
  id: string,
): CustomToolHeaderIn[] {
  return group.headers.map((h) =>
    h.name === header
      ? { name: h.name, secret: id, scheme: h.scheme }
      : h.secret
        ? { name: h.name, secret: h.secret, scheme: h.scheme }
        : { name: h.name, value: h.value ?? "" },
  );
}
