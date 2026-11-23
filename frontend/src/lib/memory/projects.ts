// frontend/src/lib/memory/projects.ts — small facts about the memory hub's
// project folders and topic files, shared by the Memory page's panes.
import type { MemoryProject, MemoryTopic } from "@/lib/api/memoryTypes";

/** A git host prefix as a project folder starts with it: `github.com-`,
 *  `git.garena.com-`, `gitlab.com-`, `bitbucket.org-`. A dotted name that is
 *  not a git host (`yuxing.wu-blackcat`) is left alone. */
const GIT_HOST_PREFIX =
  /^(?:(?:[a-z0-9-]+\.)*git[a-z0-9-]*\.[a-z]{2,}(?:\.[a-z]{2,})?|bitbucket\.org)-/i;

/** A project folder's display name: the folder without its git host prefix
 *  (`github.com-acme-payments` → `acme-payments`), or the folder itself. */
export function projectName(folder: string): string {
  const host = GIT_HOST_PREFIX.exec(folder);
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
