// frontend/src/components/memory/MemoryPane.tsx — the selected memory.
//
// Its title, the meta line "Learned by Claude Code, Codex · updated <date>"
// taken from its provenance, and its body rendered as Markdown (spec memory
// "Present a partition as its memories"). The daemon hands the body without
// its frontmatter, so frontmatter never renders as text; the provenance is
// reduced to agent names — never a native path or an agent's original text.
// The one per-memory action is Edit (spec memory "Edit a memory in the web UI
// or on disk"): it swaps the body for MemoryEditor, with Discard and Save in
// the header, and a save refused as changed on disk goes through the same
// Compare / Copy my text / Reload way out the knowledge editor has. No delete
// or file action: the partition's ⋯ menu reveals the folder. Title 15/600,
// meta 12, body 13, 620 wide.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { EditingActions } from "@/components/knowledge/KnowledgeDocumentActions";
import { KnowledgeCompareView } from "@/components/knowledge/KnowledgeCompareView";
import { FILE_PANE_SCROLL } from "@/components/filePane";
import { Markdown } from "@/components/Markdown";
import { MemoryEditor } from "@/components/memory/MemoryEditor";
import { learnedByLabels } from "@/components/memory/memoryAgents";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { NoteOut } from "@/lib/api/memoryTypes";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useMemoryNote, useSaveMemoryNote } from "@/lib/hooks/useMemory";
import { whenLabel } from "@/lib/knowledge/changes";
import { currentBodyOf, currentFingerprintOf } from "@/lib/knowledge/documentConflict";
import { formatDateTime } from "@/lib/utils";

interface Props {
  uid: string;
  slug: string;
  /** The partition's display name: whose memory the unsaved-edits prompt names. */
  partitionName: string;
}

export function MemoryPane({ uid, slug, partitionName }: Props) {
  const { t } = useTranslation();
  const note = useMemoryNote(uid, slug);

  if (note.isPending) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (note.error || !note.data) {
    return (
      <p className="text-sm text-danger">
        {t("memory.memories.loadFailed")} {note.error ? translateApiError(t, note.error) : null}
      </p>
    );
  }
  return (
    // Keyed by memory: a draft belongs to one memory only.
    <LoadedMemory
      key={slug}
      uid={uid}
      slug={slug}
      partitionName={partitionName}
      memory={note.data}
      reload={() => note.refetch()}
    />
  );
}

interface LoadedProps {
  uid: string;
  slug: string;
  partitionName: string;
  memory: NoteOut;
  reload: () => Promise<unknown>;
}

function LoadedMemory({ uid, slug, partitionName, memory: m, reload }: LoadedProps) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const saveNote = useSaveMemoryNote(uid, slug);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [savingOver, setSavingOver] = useState(false);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const draft = useFileDraft({
    loaded: m.body,
    fingerprint: m.fingerprint,
    save: (body, expected) => saveNote(body, expected ?? ""),
    reload,
    guard: { file: `${slug}.md`, owner: partitionName },
  });
  const discard = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());
  // What the disk says now, as the refusal carried it.
  const onDisk = draft.conflict ? (currentBodyOf(draft.error) ?? m.body) : null;

  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("knowledge.editor.copied")),
      () => toast.error(t("knowledge.editor.copyFailed")),
    );
  const takeDisk = () => {
    setComparing(false);
    void draft.discardAndReload().then(() => toast.success(t("knowledge.editor.reloaded")));
  };
  // "Save my edit": a second save over the disk's version, naming the
  // fingerprint the refusal carried.
  const saveOver = async () => {
    setSavingOver(true);
    try {
      const fingerprint = currentFingerprintOf(draft.error);
      const fresh =
        fingerprint ?? ((await reload()) as { data?: NoteOut } | undefined)?.data?.fingerprint;
      await saveNote(draft.value, fresh ?? "");
      setComparing(false);
      draft.cancel();
      await reload();
    } catch (error) {
      toast.error(translateApiError(t, error));
    } finally {
      setSavingOver(false);
    }
  };

  const agents = learnedByLabels(m.origins);
  const date = formatDateTime(m.updated_at);

  const actions = !draft.editing ? (
    <Button
      variant="outline"
      onClick={() => {
        setStartedAt(new Date().toISOString());
        draft.startEditing();
      }}
    >
      <Pencil aria-hidden /> {t("common.edit")}
    </Button>
  ) : comparing ? (
    <EditingActions
      dirty
      notSaved
      saving={false}
      onDiscard={discard}
      onSave={draft.save}
      statusOnly
    />
  ) : (
    <EditingActions
      dirty={draft.dirty}
      notSaved={draft.conflict}
      saving={draft.saving}
      onDiscard={discard}
      onSave={draft.save}
    />
  );

  let body;
  if (draft.editing && comparing && onDisk !== null) {
    body = (
      <KnowledgeCompareView
        name={`${slug}.md`}
        mine={draft.value}
        onDisk={onDisk}
        mineMeta={t("knowledge.compare.mineMeta", {
          when: whenLabel(t, startedAt ?? new Date().toISOString(), i18n.language),
        })}
        diskMeta={t("knowledge.compare.diskUnknown")}
        saving={savingOver}
        onBack={() => setComparing(false)}
        onSaveMine={() => void saveOver()}
        onUseDisk={takeDisk}
      />
    );
  } else if (draft.editing) {
    body = (
      <MemoryEditor
        title={m.title}
        draft={draft}
        conflictText={t("knowledge.editor.conflictUnknown", { file: `${slug}.md` })}
        onCompare={() => setComparing(true)}
        onCopyMine={copyMine}
        onReload={takeDisk}
        onDiscard={discard}
      />
    );
  } else {
    body = (
      <div className={FILE_PANE_SCROLL}>
        <div className="max-w-[620px] text-sm">
          <Markdown>{m.body}</Markdown>
        </div>
      </div>
    );
  }

  return (
    <article className="flex min-h-0 flex-1 flex-col gap-4" data-testid="memory-pane">
      <header className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h2 className="text-md font-semibold text-text">{m.title}</h2>
          <p className="text-xs text-text-muted" data-testid="memory-meta">
            {agents.length > 0
              ? t("memory.memories.learnedBy", { agents: agents.join(", "), date })
              : t("memory.memories.updated", { date })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      </header>
      {body}
      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={() => {
          setConfirmDiscard(false);
          draft.cancel();
        }}
      />
    </article>
  );
}
