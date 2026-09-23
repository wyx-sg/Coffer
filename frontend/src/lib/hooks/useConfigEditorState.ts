// frontend/src/lib/hooks/useConfigEditorState.ts — spec agent-registry.
// All state + data plumbing for the agent config editor, extracted from
// AgentConfigFilesEditor.tsx so the component stays inside the size cap. It
// owns the selection (file / directory / child), the read queries behind the
// right pane, and the draft/save state for the selected file — the last of
// which it delegates to the shared useFileDraft, since the skill master-file
// editor needs exactly the same behaviour.
//
// Changing the selection replaces the loaded content, which drops the draft
// (useFileDraft). So while the draft is dirty a selection is not applied
// directly: it is parked as `pendingSelection` for the component to confirm
// with the user, then applied (or dropped) through the two resolvers below.
import { useState } from "react";

import type { ConfigFileInfo } from "@/lib/api/agents";
import { agentsApi } from "@/lib/api/agents";
import {
  useAgentConfigChild,
  useAgentConfigFile,
  useAgentConfigFiles,
} from "@/lib/hooks/useAgents";
import { useFileDraft } from "@/lib/hooks/useFileDraft";

// Surface only config entries that actually exist on disk: a single file the
// agent has not created yet (`exists === false`) or a directory with no files
// is dropped rather than shown as a dimmed "not created" / "empty" row. The
// curated allowlist still bounds WHAT may appear (and the REST/CLI write path
// still sees absent entries) — this just keeps the read-only viewer to things
// the user can actually open.
export function visibleConfigFiles(files: ConfigFileInfo[]): ConfigFileInfo[] {
  return files.filter((f) => (f.kind === "directory" ? (f.files ?? []).length > 0 : f.exists));
}

export function useConfigEditorState(agentUid: string) {
  const files = useAgentConfigFiles(agentUid);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // When set, the selection is a child file inside the directory-backed
  // config key `selectedKey` (relpath within that directory).
  const [selectedChild, setSelectedChild] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  // A selection change held back because the draft is dirty; `null` = none.
  const [pendingSelection, setPendingSelection] = useState<(() => void) | null>(null);

  const selectedInfo = (files.data ?? []).find((f) => f.key === selectedKey);
  const isDirSelected = !selectedChild && selectedInfo?.kind === "directory";

  // Top-level file content — gated off for directory nodes (the directory key
  // itself has no content) and while a child is the active selection.
  const file = useAgentConfigFile(agentUid, selectedChild || isDirSelected ? null : selectedKey);
  const child = useAgentConfigChild(agentUid, selectedKey ?? "", selectedChild ?? "");

  // The curated allowlist (spec agent-registry "List an agent's config files with
  // their locations"), filtered
  // to entries that exist on disk — not-yet-created files and empty directories
  // are hidden.
  const allFiles = visibleConfigFiles(files.data ?? []);

  const activeQuery = selectedChild ? child : file;
  const activeContent = activeQuery.data;
  const memoryBlock = activeContent?.memory_block === true;

  // A file the agent has not created yet reads as empty with `exists: false`.
  // Saving one would create it from the UI, which the allowlist deliberately
  // does not do here — the write path creates children of a directory entry,
  // not top-level files.
  const readOnlyMissing = !selectedChild && activeContent?.exists === false;

  const draft = useFileDraft({
    loaded: activeContent?.content,
    fingerprint: activeContent?.fingerprint,
    save: async (content, expectedFingerprint) => {
      const key = selectedKey as string;
      const body = { content, expected_fingerprint: expectedFingerprint };
      if (selectedChild) await agentsApi.writeConfigChild(agentUid, key, selectedChild, body);
      else await agentsApi.writeConfigFile(agentUid, key, body);
      // Neither write returns the new content fingerprint (both answer with the
      // file's metadata), so the next save re-reads for it via the reload below.
      return undefined;
    },
    reload: () => activeQuery.refetch(),
  });

  // Apply a selection now, or park it while unsaved edits are on screen.
  function guarded(apply: () => void) {
    if (draft.dirty) setPendingSelection(() => apply);
    else apply();
  }

  function selectFile(key: string) {
    guarded(() => {
      setSelectedKey(key);
      setSelectedChild(null);
    });
  }

  function selectDirectory(key: string) {
    guarded(() => {
      setSelectedKey(key);
      setSelectedChild(null);
      setExpandedDirs((prev) => ({ ...prev, [key]: !prev[key] }));
    });
  }

  function selectChild(key: string, relpath: string) {
    guarded(() => {
      setSelectedKey(key);
      setSelectedChild(relpath);
    });
  }

  /** The user chose to drop the draft: apply the parked selection. */
  function confirmPendingSelection() {
    const apply = pendingSelection;
    setPendingSelection(null);
    if (!apply) return;
    draft.cancel();
    apply();
  }

  function cancelPendingSelection() {
    setPendingSelection(null);
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
    readOnlyMissing,
    draft,
    /** True while a selection waits on the discard-changes confirmation. */
    hasPendingSelection: pendingSelection !== null,
    confirmPendingSelection,
    cancelPendingSelection,
  };
}
