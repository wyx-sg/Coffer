// src/components/agents/list/useFolderListing.ts — what a candidate config directory holds, as far as the daemon shows it.
//
// The daemon's folder browse lists subdirectories only, never files (spec
// daemon "Browse folders without reading files"), so a folder entry of the
// type (skills/) is checked here and the files are named without a verdict.
import type { AgentType } from "@/lib/api/agents";
import { useFsBrowse } from "@/lib/hooks/useFsBrowse";

export interface KeptEntry {
  name: string;
  /** i18n key of what the entry holds. */
  role: string;
  folder: boolean;
}

const KEPT: Record<AgentType, KeptEntry[]> = {
  claude_code: [
    { name: "settings.json", role: "agents.configDirDialog.role.settings", folder: false },
    { name: "CLAUDE.md", role: "agents.configDirDialog.role.instructions", folder: false },
    { name: "skills", role: "agents.configDirDialog.role.skills", folder: true },
    { name: ".claude.json", role: "agents.configDirDialog.role.mcpAt", folder: false },
  ],
  codex: [
    { name: "config.toml", role: "agents.configDirDialog.role.codexConfig", folder: false },
    { name: "AGENTS.md", role: "agents.configDirDialog.role.instructions", folder: false },
    { name: "hooks.json", role: "agents.configDirDialog.role.hooks", folder: false },
    { name: "skills", role: "agents.configDirDialog.role.skills", folder: true },
  ],
};

export function keptEntries(type: AgentType): KeptEntry[] {
  return KEPT[type];
}

/** `path` null or empty reads nothing. `folders` = the subdirectory names there; `missing` = the path is not a readable folder. */
export function useFolderListing(path: string | null) {
  const enabled = !!path;
  const top = useFsBrowse(path, { enabled });
  const folders = new Set((top.data?.entries ?? []).map((e) => e.name));
  const skillsPath = path && folders.has("skills") ? `${path.replace(/\/+$/, "")}/skills` : null;
  const skills = useFsBrowse(skillsPath, { enabled: !!skillsPath });
  return {
    isPending: enabled && top.isPending,
    missing: enabled && top.isError,
    folders,
    skillFolders: skills.data?.entries.length,
  };
}
