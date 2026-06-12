// frontend/src/lib/hooks/useConfigEditorState.ts — spec 004.
// All state + data plumbing for the agent config editor, extracted from
// AgentConfigFilesEditor.tsx so the component stays inside the size cap.
// Owns the selection (file / directory / child), the editable draft, the
// save/create/delete mutations with their fingerprints (409 CONFIG_FILE_STALE
// surfaces as `stale`), and the new-file / delete-child dialog state.
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import {
  useAgentConfigChild,
  useAgentConfigFile,
  useAgentConfigFiles,
  useDeleteConfigChild,
  useSaveAgentConfigFile,
  useWriteConfigChild,
} from "@/lib/hooks/useAgents";

// Mirror of the server-side rules for a relpath created under a
// directory-backed config key: markdown only, relative, no traversal.
export function isValidChildRelpath(relpath: string): boolean {
  if (!relpath.endsWith(".md") || relpath === ".md") return false;
  if (relpath.startsWith("/")) return false;
  if (relpath.includes("..")) return false;
  return true;
}

function isStaleError(error: unknown): boolean {
  return error instanceof ApiError && error.code === "CONFIG_FILE_STALE";
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
  const file = useAgentConfigFile(
    name,
    selectedChild || isDirSelected ? null : selectedKey,
  );
  const child = useAgentConfigChild(name, selectedKey ?? "", selectedChild ?? "");
  const save = useSaveAgentConfigFile(name);
  const saveChild = useWriteConfigChild(name);
  const createChild = useWriteConfigChild(name);
  const deleteChild = useDeleteConfigChild(name);

  // The full curated allowlist (FR-014 / User Story 7), including
  // not-yet-created files: the user can open one — it reads as empty without
  // being created — edit, and save to create it. Absent files are dimmed.
  const allFiles = files.data ?? [];

  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showFind, setShowFind] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // New-file dialog (per directory node) + delete-child confirm dialog.
  const [newFileDir, setNewFileDir] = useState<string | null>(null);
  const [newFileName, setNewFileName] = useState("");
  const [newFileInvalid, setNewFileInvalid] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ key: string; relpath: string } | null>(null);

  const activeQuery = selectedChild ? child : file;
  const activeContent = activeQuery.data;
  const activeSave = selectedChild ? saveChild : save;
  const stale = isStaleError(activeSave.error);
  const memoryBlock = activeContent?.memory_block === true;

  // Seed (and re-seed) the draft from the fetched content whenever the loaded
  // file changes, unless the user already has unsaved edits in flight.
  const fetched = activeContent?.content ?? "";
  useEffect(() => {
    if (!dirty) setDraft(fetched);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetched, selectedKey, selectedChild]);

  function resetEditorState() {
    setDirty(false);
    setSaved(false);
    save.reset();
    saveChild.reset();
  }

  function selectFile(key: string) {
    setSelectedKey(key);
    setSelectedChild(null);
    resetEditorState();
  }

  function selectDirectory(key: string) {
    setSelectedKey(key);
    setSelectedChild(null);
    setExpandedDirs((prev) => ({ ...prev, [key]: !prev[key] }));
    resetEditorState();
  }

  function selectChild(key: string, relpath: string) {
    setSelectedKey(key);
    setSelectedChild(relpath);
    resetEditorState();
  }

  function updateDraft(next: string) {
    setDraft(next);
    setDirty(true);
    setSaved(false);
  }

  function onSave() {
    if (!selectedKey) return;
    const onSuccess = () => {
      setDirty(false);
      setSaved(true);
    };
    if (selectedChild) {
      saveChild.mutate(
        {
          key: selectedKey,
          relpath: selectedChild,
          content: draft,
          expected_fingerprint: child.data?.fingerprint,
        },
        { onSuccess },
      );
    } else {
      save.mutate(
        { key: selectedKey, content: draft, expected_fingerprint: file.data?.fingerprint },
        { onSuccess },
      );
    }
  }

  // 409 CONFIG_FILE_STALE → the file changed on disk since it was read.
  // Reload refetches the content query (the seed effect then replaces the
  // draft, since dirty is cleared) and clears the banner via mutation reset.
  function onReloadStale() {
    if (selectedChild) child.refetch();
    else file.refetch();
    resetEditorState();
  }

  function openNewFileDialog(dirKey: string) {
    setNewFileDir(dirKey);
    setNewFileName("");
    setNewFileInvalid(false);
    createChild.reset();
  }

  function setNewFileNameValid(next: string) {
    setNewFileName(next);
    setNewFileInvalid(false);
  }

  function submitNewFile() {
    if (!newFileDir) return;
    const relpath = newFileName.trim();
    if (!isValidChildRelpath(relpath)) {
      setNewFileInvalid(true);
      return;
    }
    createChild.mutate(
      { key: newFileDir, relpath, content: "" },
      {
        onSuccess: () => {
          setExpandedDirs((prev) => ({ ...prev, [newFileDir]: true }));
          selectChild(newFileDir, relpath);
          setNewFileDir(null);
        },
      },
    );
  }

  function confirmDeleteChild() {
    if (!deleteTarget) return;
    deleteChild.mutate(deleteTarget, {
      onSuccess: () => {
        if (selectedChild === deleteTarget.relpath && selectedKey === deleteTarget.key) {
          setSelectedChild(null);
          resetEditorState();
        }
        setDeleteTarget(null);
      },
    });
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
    draft,
    dirty,
    saved,
    updateDraft,
    onSave,
    showFind,
    setShowFind,
    textareaRef,
    activeQuery,
    activeContent,
    activeSave,
    stale,
    onReloadStale,
    memoryBlock,
    newFileDir,
    setNewFileDir,
    newFileName,
    setNewFileNameValid,
    newFileInvalid,
    createChild,
    openNewFileDialog,
    submitNewFile,
    deleteTarget,
    setDeleteTarget,
    deleteChild,
    confirmDeleteChild,
  };
}
