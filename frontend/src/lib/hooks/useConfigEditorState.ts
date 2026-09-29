// frontend/src/lib/hooks/useConfigEditorState.ts — spec agent-registry.
// All state + data plumbing for the agent's Config files tab, kept apart from
// the components so they stay inside the size cap. It owns the selection
// (file / directory / child — kept in the URL as `?file=<key>[/<relpath>]` so a
// reload or a link opens the same file), the read queries behind the right
// pane, and the draft/save state for the selected file — the last of which it
// delegates to the shared useFileDraft.
//
// Every allowlisted entry is listed, including a file the agent has not created
// yet: the tab shows the instructions files beside the settings files, and a
// missing one can be created from here (the write creates it).
//
// Changing the selection replaces the loaded content, which drops the draft
// (useFileDraft). So while the draft is dirty a selection is not applied
// directly: it is parked as `pendingSelection` for the component to confirm
// with the user, then applied (or dropped) through the two resolvers below.
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { agentsApi } from "@/lib/api/agents";
import {
  useAgentConfigChild,
  useAgentConfigFile,
  useAgentConfigFiles,
} from "@/lib/hooks/useAgents";
import { useFileDraft } from "@/lib/hooks/useFileDraft";

/** `?file=` → the selected key and, for a directory entry's file, its relpath. */
function parseFileParam(value: string | null): { key: string | null; child: string | null } {
  if (!value) return { key: null, child: null };
  const slash = value.indexOf("/");
  if (slash < 0) return { key: value, child: null };
  return { key: value.slice(0, slash), child: value.slice(slash + 1) || null };
}

export function useConfigEditorState(agentUid: string) {
  const files = useAgentConfigFiles(agentUid);
  const [params, setParams] = useSearchParams();
  const { key: selectedKey, child: selectedChild } = parseFileParam(params.get("file"));
  // Directories start open (the tree shows their files); a click folds one.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  // A selection change held back because the draft is dirty; `null` = none.
  const [pendingSelection, setPendingSelection] = useState<(() => void) | null>(null);

  const allFiles = files.data ?? [];
  const selectedInfo = allFiles.find((f) => f.key === selectedKey);
  const isDirSelected = !selectedChild && selectedInfo?.kind === "directory";

  // Top-level file content — gated off for directory nodes (the directory key
  // itself has no content) and while a child is the active selection.
  const file = useAgentConfigFile(agentUid, selectedChild || isDirSelected ? null : selectedKey);
  const child = useAgentConfigChild(agentUid, selectedKey ?? "", selectedChild ?? "");

  const activeQuery = selectedChild ? child : file;
  const activeContent = activeQuery.data;
  /** The selected top-level file is not on disk yet; saving creates it. */
  const missing = !selectedChild && activeContent?.exists === false;

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
    reload: async () => {
      await activeQuery.refetch();
      // A created file changes the listing (exists, size), not only the content.
      if (missing) await files.refetch();
    },
  });

  function setFileParam(value: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("file", value);
        return next;
      },
      { replace: true },
    );
  }

  // Apply a selection now, or park it while unsaved edits are on screen.
  function guarded(apply: () => void) {
    if (draft.dirty) setPendingSelection(() => apply);
    else apply();
  }

  function selectFile(key: string) {
    guarded(() => setFileParam(key));
  }

  function selectDirectory(key: string) {
    guarded(() => {
      setFileParam(key);
      // Re-clicking the open directory folds it; picking another one opens it.
      setCollapsed((prev) => ({
        ...prev,
        [key]: selectedKey === key && !selectedChild && !prev[key],
      }));
    });
  }

  function selectChild(key: string, relpath: string) {
    guarded(() => setFileParam(`${key}/${relpath}`));
  }

  /** The user chose to drop the draft: apply the parked selection. */
  function confirmPendingSelection() {
    const apply = pendingSelection;
    setPendingSelection(null);
    if (!apply) return;
    draft.cancel();
    apply();
  }

  return {
    files,
    allFiles,
    selectedKey,
    selectedChild,
    selectedInfo,
    isDirSelected,
    collapsed,
    selectFile,
    selectDirectory,
    selectChild,
    activeQuery,
    activeContent,
    missing,
    draft,
    /** True while a selection waits on the discard-changes confirmation. */
    hasPendingSelection: pendingSelection !== null,
    confirmPendingSelection,
    cancelPendingSelection: () => setPendingSelection(null),
  };
}
