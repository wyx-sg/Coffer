// frontend/src/lib/memory/projects.ts — small facts about the memory hub's
// project folders and topic files, shared by the Memory page's panes.
import type { MemoryProject, MemoryTopic } from "@/lib/api/memoryTypes";

/** A project folder's short name: its last `-`-separated part after the host
 *  (`github.com-acme-payments` → `acme-payments`), or the folder itself. */
export function projectName(folder: string): string {
  const host = /^[a-z0-9-]+\.[a-z]{2,}(?:\.[a-z]{2,})?-/i.exec(folder);
  return host ? folder.slice(host[0].length) : folder;
}

/** The project the page opens on: the one updated most recently. */
export function defaultProject(projects: readonly MemoryProject[]): string | null {
  let best: MemoryProject | null = null;
  for (const p of projects) if (!best || p.updated > best.updated) best = p;
  return best?.folder ?? null;
}

/** How many memories a topic holds: its non-empty lines. */
export function memoryCount(topic: Pick<MemoryTopic, "body">): number {
  return topic.body.split("\n").filter((l) => l.trim()).length;
}

/** Every topic file across the hub. */
export function totalTopics(projects: readonly MemoryProject[]): number {
  return projects.reduce((n, p) => n + p.topics, 0);
}
