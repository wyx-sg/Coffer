// frontend/src/pages/sync/syncConflictTestKit.ts — wire-shaped fixtures for
// the conflict and held-deletion tests, typed against the generated contract
// so a field renamed on the backend fails every test that builds one.
import type { ConflictFile, FileVersions, StoppedRound, SyncHold } from "@/lib/api/sync";

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
    agent_merge: false,
    ...over,
  };
}

export function makeStopped(files: ConflictFile[], over: Partial<StoppedRound> = {}): StoppedRound {
  return {
    kind: "conflicts",
    raised_at: "2026-09-13T09:00:00Z",
    local: "aaa",
    remote: "bbb",
    join: null,
    files,
    unanswered: files.filter((f) => f.answer === null).length,
    hold: null,
    handoff: null,
    ...over,
  };
}

export function makeHold(over: Partial<SyncHold> = {}): SyncHold {
  const chat = Array.from({ length: 12 }, (_, i) => `knowledge/archive/chat-bot/n${i + 1}.md`);
  const pdf = ["skills/pdf-tools-old/SKILL.md", "skills/pdf-tools-old/scripts/extract.py"];
  return {
    direction: "incoming",
    breaches: [{ area: "knowledge", lost: 12, total: 20 }],
    paths: [...chat, ...pdf],
    groups: [
      { folder: "knowledge/archive/chat-bot", paths: chat, total: 20 },
      { folder: "skills/pdf-tools-old", paths: pdf, total: 2 },
    ],
    machines: ["Mac mini"],
    confirmed: false,
    ...over,
  };
}

export function makeHeldRound(hold: SyncHold = makeHold()): StoppedRound {
  return makeStopped([], { kind: "hold", hold, unanswered: 0 });
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
    base: null,
    take_theirs: TAKE_THEIRS_DIFF,
    binary: false,
    edited: null,
    ...over,
  };
}
