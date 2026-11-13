// frontend/src/pages/sync/syncConflictTestKit.ts — wire-shaped fixtures for
// the conflict tests, typed against the generated contract
// so a field renamed on the backend fails every test that builds one.
import type { ConflictFile, FileVersions, StoppedRound } from "@/lib/api/sync";

export function makeConflict(path: string, over: Partial<ConflictFile> = {}): ConflictFile {
  return {
    path,
    area: path.split("/")[0] ?? "knowledge",
    reason: "both_changed",
    ours_time: "2026-09-13T08:00:00Z",
    theirs_time: "2026-09-13T08:30:00Z",
    theirs_machine: "Mac mini",
    other_path: null,
    answer: null,
    editor_path: null,
    secret: false,
    agent_mergeable: false,
    agent_state: null,
    agent_handed_at: null,
    agent_name: null,
    agent_conversation_id: null,
    agent_merged_at: null,
    ...over,
  };
}

export function makeStopped(files: ConflictFile[], over: Partial<StoppedRound> = {}): StoppedRound {
  return {
    raised_at: "2026-09-13T09:00:00Z",
    local: "aaa",
    remote: "bbb",
    join: null,
    files,
    unanswered: files.filter((f) => f.answer === null).length,
    ...over,
  };
}

const TAKE_THEIRS_DIFF = [
  "--- this machine/skills/coffer-guide/SKILL.md",
  "+++ Mac mini/skills/coffer-guide/SKILL.md",
  "@@ -14,4 +14,4 @@ ## When to load",
  " ## When to load",
  "-Load it before asking.",
  "+Load it first.",
  "-Paths live under ~/.coffer/knowledge/.",
  "+Paths live under ~/.coffer/vault/knowledge/.",
  " ",
  "",
].join("\n");

export function makeVersions(path: string, over: Partial<FileVersions> = {}): FileVersions {
  return {
    path,
    ours: "mine\n",
    theirs: "theirs\n",
    take_theirs: TAKE_THEIRS_DIFF,
    binary: false,
    ...over,
  };
}
