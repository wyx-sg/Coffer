// frontend/src/lib/hooks/useConfigEditorState.ts — spec 004.
// All state + data plumbing for the read-only agent config viewer, extracted
// from AgentConfigFilesEditor.tsx so the component stays inside the size cap.
// Config files are viewed in-app and edited in the user's own editor, so this
// hook only owns the selection (file / directory / child) and the read queries
// that back the right-pane preview — no draft, save, fingerprint, or dialog
// state.
import { useState } from "react";

import type { ConfigFileInfo } from "@/lib/api/agents";
import {
  useAgentConfigChild,
  useAgentConfigFile,
  useAgentConfigFiles,
} from "@/lib/hooks/useAgents";

// Surface only config entries that actually exist on disk: a single file the
// agent has not created yet (`exists === false`) or a directory with no files
// is dropped rather than shown as a dimmed "not created" / "empty" row. The
// curated allowlist still bounds WHAT may appear (and the REST/CLI write path
// still sees absent entries) — this just keeps the read-only viewer to things
// the user can actually open.
export function visibleConfigFiles(files: ConfigFileInfo[]): ConfigFileInfo[] {
  return files.filter((f) => (f.kind === "directory" ? (f.files ?? []).length > 0 : f.exists));
}

export function useConfigEditorState(name: string) {
  const files = useAgentConfigFiles(name);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // When set, the selection is a child file inside the directory-backed
  // config key `selectedKey` (relpath within that directory).
  const [selectedChild, setSelectedChild] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});

  const selectedInfo = (files.data ?? []).find((f) => f.key === selectedKey);
  const isDirSelected = !selectedChild && selectedInfo?.kind === "directory";

  // Top-level file content — gated off for directory nodes (the directory key
  // itself has no content) and while a child is the active selection.
  const file = useAgentConfigFile(name, selectedChild || isDirSelected ? null : selectedKey);
  const child = useAgentConfigChild(name, selectedKey ?? "", selectedChild ?? "");

  // The curated allowlist (FR-014 / User Story 7), filtered to entries that
  // exist on disk — not-yet-created files and empty directories are hidden.
  const allFiles = visibleConfigFiles(files.data ?? []);

  const activeQuery = selectedChild ? child : file;
  const activeContent = activeQuery.data;
  const memoryBlock = activeContent?.memory_block === true;

  function selectFile(key: string) {
    setSelectedKey(key);
    setSelectedChild(null);
  }

  function selectDirectory(key: string) {
    setSelectedKey(key);
    setSelectedChild(null);
    setExpandedDirs((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function selectChild(key: string, relpath: string) {
    setSelectedKey(key);
    setSelectedChild(relpath);
  }

  return {
    files,
    allFiles,
    selectedKey,
    selectedChild,
    selectedInfo,
    isDirSelected,
    expandedDirs,
    selectFile,
    selectDirectory,
    selectChild,
    activeQuery,
    activeContent,
    memoryBlock,
  };
}
