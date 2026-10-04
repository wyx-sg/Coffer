// src/components/skills/skillSourceHelpers.ts
// Pure helpers for the skill source surfaces: path cleaning, archive names, the found step's choice rules, commit and repository labels, unified-diff rows.
import { ApiError } from "@/lib/api/errors";
import type { ChangeOp, DiffLine } from "@/lib/changePreview/changeCounts";
import type { SkillFileChange, SkillStaging, StagedSkill } from "@/lib/api/skills";

/** A pasted path often carries quotes (a shell's "Copy as path") or a trailing newline. */
export function cleanPath(raw: string): string {
  const trimmed = raw.trim();
  const m = /^(["'])(.*)\1$/.exec(trimmed);
  return (m ? m[2] : trimmed).trim();
}

/** A change bigger than one keystroke: a paste, or a folder chosen with the picker. */
export function isJump(prev: string, next: string): boolean {
  if (Math.abs(next.length - prev.length) > 1) return true;
  return !next.startsWith(prev) && !prev.startsWith(next);
}

export const ARCHIVE_ACCEPT = ".zip,.skill";

/** True for a file the archive source takes (`.zip` or `.skill`). */
export function isArchiveFile(file: File): boolean {
  return /\.(zip|skill)$/i.test(file.name);
}

/** A staged skill the user may choose: valid, named, and not a built-in's name. */
export function isChoosable(skill: StagedSkill): skill is StagedSkill & { name: string } {
  return skill.valid && !!skill.name && !skill.protected;
}

/** One choosable skill is preselected; several start with none, so every add is a choice. */
export function defaultSelection(stage: SkillStaging): Set<string> {
  const choosable = stage.skills.filter(isChoosable);
  return new Set(stage.skills.length === 1 && choosable.length === 1 ? [choosable[0].name] : []);
}

/** The first seven characters of a commit id, as git prints it. */
export function shortCommit(commit: string | null | undefined): string {
  return (commit ?? "").slice(0, 7);
}

/** A repository URL as a person reads it: no scheme, no trailing `.git`. */
export function repoLabel(url: string): string {
  return url
    .replace(/^[a-z][a-z0-9+.-]*:\/\//i, "")
    .replace(/\.git$/, "")
    .replace(/\/$/, "");
}

/** `owner/repo` of a repository URL, as the clone line and its failure name it. */
export function repoName(url: string): string {
  const label = repoLabel(url.trim());
  return /^[^/:]+[/:](.+)$/.exec(label)?.[1] ?? label;
}

/** The host a repository URL names, for "Couldn't reach github.com". */
/** The refusals that get a problem block: they depend on this machine, so an agent can help. */
export function isMachineProblem(error: unknown): boolean {
  return error instanceof ApiError && error.code === "SKILL_SOURCE_UNREACHABLE";
}

/** What git itself said, without Coffer's "git clone failed:" lead-in or git's "fatal:" tag. */
export function gitSays(message: string): string {
  return message.replace(/^git \S+ failed:\s*/i, "").replace(/^(fatal|error):\s*/i, "");
}

export const CHANGE_OP: Record<SkillFileChange["status"], ChangeOp> = {
  added: "add",
  removed: "remove",
  modified: "modify",
};

const REVERSED_STATUS: Record<SkillFileChange["status"], SkillFileChange["status"]> = {
  added: "removed",
  removed: "added",
  modified: "modified",
};

/** The same change read the other way round — what happens to the side a
 *  dialog's other choice would keep: `+` and `-` lines swap, each hunk's two
 *  ranges swap, an added file becomes a removed one. */
export function reverseChange(change: SkillFileChange): SkillFileChange {
  const diff = change.diff
    .split("\n")
    .map((line) => {
      if (line.startsWith("+++ ") || line.startsWith("--- ")) return line;
      const hunk = /^@@ -(\S+) \+(\S+) @@(.*)$/.exec(line);
      if (hunk) return `@@ -${hunk[2]} +${hunk[1]} @@${hunk[3]}`;
      if (line.startsWith("+")) return `-${line.slice(1)}`;
      if (line.startsWith("-")) return `+${line.slice(1)}`;
      return line;
    })
    .join("\n");
  return {
    ...change,
    status: REVERSED_STATUS[change.status],
    diff,
    additions: change.deletions,
    deletions: change.additions,
  };
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/** Split a unified diff into rows with their old and new line numbers; file headers are dropped. */
export function parseUnifiedDiff(diff: string): DiffLine[] {
  const out: DiffLine[] = [];
  let oldNo = 0;
  let newNo = 0;
  let inHunk = false;
  const rows = diff.split("\n");
  // The split leaves an empty string after the last newline; it is not a line.
  if (rows.length > 0 && rows[rows.length - 1] === "") rows.pop();
  for (const raw of rows) {
    const hunk = HUNK.exec(raw);
    if (hunk) {
      oldNo = Number(hunk[1]);
      newNo = Number(hunk[2]);
      inHunk = true;
      out.push({ kind: "hunk", text: raw });
      continue;
    }
    if (!inHunk || raw.startsWith("\\")) continue;
    if (raw.startsWith("+")) {
      out.push({ kind: "add", text: raw.slice(1), newNo: newNo++ });
    } else if (raw.startsWith("-")) {
      out.push({ kind: "remove", text: raw.slice(1), oldNo: oldNo++ });
    } else if (raw.startsWith(" ") || raw === "") {
      out.push({ kind: "context", text: raw.slice(1), oldNo: oldNo++, newNo: newNo++ });
    }
  }
  return out;
}
