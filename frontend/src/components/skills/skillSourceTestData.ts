// src/components/skills/skillSourceTestData.ts
// Test fixtures for the Git source panel and the update dialog: a Git-imported skill, one with an update waiting, and a change of source.
import type { SkillOut, SkillSourceChange, SkillSourceStatus } from "@/lib/api/skills";

export function gitSkill(status: Partial<SkillSourceStatus> | null = {}): SkillOut {
  return {
    uid: "sk-1",
    name: "terraform-plan",
    description: "Read a plan like a reviewer.",
    builtin: false,
    enabled: true,
    scope: null,
    bindings: [],
    requires: [],
    requires_declared: true,
    requires_secrets: [],
    requires_tools: [],
    requires_skills: [],
    master_missing: false,
    master_path: "/home/me/.coffer/skills/terraform-plan",
    version_hash: "h",
    created_at: "2026-09-18T09:00:00Z",
    updated_at: "2026-09-18T09:00:00Z",
    last_synced_from_source_at: null,
    source: {
      type: "git_import",
      url: "https://github.com/acme/agent-skills",
      ref: "main",
      subpath: "terraform-plan",
      commit: "a1b2c3d4e5f6",
      content_hash: "c",
    },
    source_status:
      status === null
        ? null
        : {
            checked_at: "2026-09-30T09:12:00Z",
            last_success_at: "2026-09-30T09:12:00Z",
            error: null,
            latest_commit: "a1b2c3d4e5f6",
            commits_ahead: 0,
            files_changed: 0,
            update_available: false,
            commits: [],
            compare_url: null,
            ...status,
          },
  };
}

/** A skill with an update waiting: `a1b2c3d` → `f9e8d7c`, on a host with a compare page by default. */
export function updatableSkill(status: Partial<SkillSourceStatus> = {}): SkillOut {
  return gitSkill({
    latest_commit: "f9e8d7c6b5a4",
    commits_ahead: 2,
    files_changed: 2,
    update_available: true,
    commits: [
      { id: "f9e8d7c6b5a4", subject: "Ask before backend changes" },
      { id: "0011223344", subject: "Add plan.sh" },
    ],
    compare_url: "https://github.com/acme/agent-skills/compare/a1b2c3d4e5f6...f9e8d7c6b5a4",
    ...status,
  });
}

/** What Change source answers: names and status, no diff. */
export function sourceChange(over: Partial<SkillSourceChange> = {}): SkillSourceChange {
  return {
    staging_id: "chg-1",
    commit: "f9e8d7c6b5a4",
    files: [
      { path: "SKILL.md", status: "modified" },
      { path: "scripts/plan.sh", status: "added" },
      { path: "old.txt", status: "removed" },
    ],
    ...over,
  };
}
