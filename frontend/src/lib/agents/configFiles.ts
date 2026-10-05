// src/lib/agents/configFiles.ts — small pure helpers for the agent's Config files tab.

/** The last segment of a path — the name the agent's own docs use for the file. */
export function baseName(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
