// src/components/custom-tools/environmentVariables.ts — an environment's variable rows as the editor holds them, and the
// map a save sends.
export interface VariableRow {
  key: string;
  value: string;
}

/** The variables a save sends: rows with a name. */
export function variablesIn(rows: readonly VariableRow[]): Record<string, string> {
  return Object.fromEntries(
    rows.filter((r) => r.key.trim() !== "").map((r) => [r.key.trim(), r.value]),
  );
}
