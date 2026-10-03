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
// (useFileDraft). The selection is a location change, so while the draft is
// dirty the shell's unsaved-changes guard (useUnsavedGuard) stops it and asks
// first; nothing here needs to hold a selection back.
import { useState } from "react";
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";

import { baseName } from "@/lib/agents/configFiles";
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

/** `owner` is the agent's name, for the unsaved-changes dialog's sentence. */
export function useConfigEditorState(agentUid: string, owner: string) {
  const files = useAgentConfigFiles(agentUid);
  const [params, setParams] = useSearchParams();
  const { key: selectedKey, child: selectedChild } = parseFileParam(params.get("file"));
  // Directories start open (the tree shows their files); a click folds one.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
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
    guard: {
      file: selectedChild ?? (selectedInfo ? baseName(selectedInfo.path) : (selectedKey ?? "")),
      owner,
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

  function selectFile(key: string) {
    setFileParam(key);
  }

  function selectDirectory(key: string) {
    setFileParam(key);
    // Re-clicking the open directory folds it; picking another one opens it.
    setCollapsed((prev) => ({
      ...prev,
      [key]: selectedKey === key && !selectedChild && !prev[key],
    }));
  }

  function selectChild(key: string, relpath: string) {
    setFileParam(`${key}/${relpath}`);
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
  };
}
