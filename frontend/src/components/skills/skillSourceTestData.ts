// src/components/skills/skillSourceTestData.ts
// Test fixtures for the Git source panel and the update dialog: a Git-imported skill and an update preview.
import type { SkillOut, SkillSourceStatus, SkillUpdatePreview } from "@/lib/api/skills";

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
            dismissed_commit: null,
            update_available: false,
            ...status,
          },
  };
}

export function updatePreview(over: Partial<SkillUpdatePreview> = {}): SkillUpdatePreview {
  return {
    staging_id: "upd-1",
    from_commit: "a1b2c3d4e5f6",
    to_commit: "f9e8d7c6b5a4",
    up_to_date: false,
    conflict: false,
    commits: [
      { id: "f9e8d7c6b5a4", subject: "Ask before backend changes" },
      { id: "0011223344", subject: "Add plan.sh" },
    ],
    changes: [
      {
        path: "SKILL.md",
        status: "modified",
        diff: "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -6,2 +6,2 @@ Steps\n ## Steps\n-- List replace or destroy.\n+- List replace, destroy or move.\n",
        binary: false,
        additions: 1,
        deletions: 1,
        truncated: false,
      },
      {
        path: "scripts/plan.sh",
        status: "added",
        diff: "@@ -0,0 +1,1 @@\n+terraform plan\n",
        binary: false,
        additions: 1,
        deletions: 0,
        truncated: false,
      },
    ],
    local_changes: [],
    ...over,
  };
}
