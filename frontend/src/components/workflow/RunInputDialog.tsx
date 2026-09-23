// frontend/src/components/workflow/RunInputDialog.tsx
// Add something for a run to read: a knowledge collection, a link, a local
// repository, a file from this machine, or a note the developer writes
// themselves.
//
// One dialog, five kinds, and the KIND decides what the second field is. That
// is the reason this is a dialog rather than the inline row it replaced: the
// row had to show every field at once, so it could not change shape, so the
// one kind whose field is not a text box — a file — could not be in the picker
// at all. It sat beside it as a separate "Upload a file" button, next to a
// picker that pointedly did not offer "File". Here the field just changes: a
// collection is chosen from the ones the vault has, a file from the disk, a
// link typed and a repository picked from this machine's folders.
//
// Two routes underneath, because the kinds carry different things: a
// collection, a link or a repository path is a REFERENCE and goes as JSON; a
// file is BYTES and goes as multipart to its own route, which stores it under
// the run's own directory. That split is the server's business, and this is
// the last place in the UI where it shows.
//
// The dialog closes only on success. A refusal — a run this machine does not
// advance, a repository that is not there — leaves the form
// standing with what the developer typed still in it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { FilePickerField } from "@/components/FilePickerField";
import { FolderPickerField } from "@/components/FolderPickerField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import {
  useAddWorkflowInput,
  useAddWorkflowNote,
  useUploadWorkflowInput,
} from "@/lib/hooks/useWorkflowInputs";
import type { RunInputKind } from "@/lib/api/workflow";

const KINDS = [
  "knowledge",
  "file",
  "note",
  "link",
  "repo",
] as const satisfies readonly RunInputKind[];

interface Props {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RunInputDialog({ runId, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const add = useAddWorkflowInput(runId);
  const upload = useUploadWorkflowInput(runId);
  const note = useAddWorkflowNote(runId);
  // Only fetched while the dialog is mounted, and only needed by one kind.
  const collections = useKnowledgeCollections();
  const [kind, setKind] = useState<RunInputKind>("knowledge");
  const [ref, setRef] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");

  const pending = add.isPending || upload.isPending || note.isPending;
  const error = add.error ?? upload.error ?? note.error;
  const incomplete = kind === "file" ? file === null : ref.trim().length === 0;

  const close = () => {
    setKind("knowledge");
    setRef("");
    setFile(null);
    setDescription("");
    onOpenChange(false);
  };

  const submit = () => {
    const label = description.trim() || null;
    if (kind === "file") {
      if (file === null) return;
      upload.mutate({ file, label }, { onSuccess: close });
      return;
    }
    if (kind === "note") {
      // A title and nothing else. The note itself is written on its own page,
      // where there is room for it, a preview, and somewhere to paste a
      // screenshot — none of which belongs in the dialog that creates it.
      note.mutate({ title: ref.trim(), text: "" }, { onSuccess: close });
      return;
    }
    add.mutate({ kind, ref: ref.trim(), label }, { onSuccess: close });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.inputs.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("workflow.inputs.dialogDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="input-kind">{t("workflow.inputs.kindLabel")}</Label>
            <Select
              value={kind}
              onValueChange={(next) => {
                // What the old field held means nothing under the new kind: a
                // collection name is not a URL and a URL is not a path.
                setKind(next as RunInputKind);
                setRef("");
                setFile(null);
              }}
            >
              <SelectTrigger id="input-kind" disabled={pending}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {t(`workflow.inputs.kinds.${option}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="input-ref">{t(`workflow.inputs.refLabels.${kind}`)}</Label>
            {kind === "knowledge" ? (
              // Chosen, not typed: the collections are a list the vault has,
              // and a typo here would point the run at nothing.
              <Combobox
                id="input-ref"
                value={ref.length > 0 ? ref : null}
                options={(collections.data ?? []).map((c) => ({
                  value: c.name,
                  label: c.name,
                  hint: c.description || undefined,
                }))}
                onChange={setRef}
                disabled={pending}
                placeholder={t("workflow.inputs.pickCollection")}
                emptyMessage={
                  (collections.data ?? []).length === 0
                    ? t("workflow.inputs.noCollections")
                    : t("workflow.inputs.noCollectionMatches")
                }
              />
            ) : kind === "repo" ? (
              // Picked, not typed, and for the same reason a collection is:
              // the browser cannot read an absolute path, so the loopback
              // daemon opens the host's own folder dialog and hands one back.
              <FolderPickerField
                inputId="input-ref"
                value={ref.length > 0 ? ref : null}
                onChange={(picked) => setRef(picked ?? "")}
                placeholder={t("workflow.inputs.refPlaceholders.repo")}
              />
            ) : kind === "file" ? (
              <FilePickerField
                inputId="input-ref"
                value={file}
                onChange={setFile}
                disabled={pending}
                placeholder={t("picker.noFile")}
              />
            ) : (
              <Input
                id="input-ref"
                value={ref}
                disabled={pending}
                onChange={(e) => setRef(e.target.value)}
                placeholder={t(`workflow.inputs.refPlaceholders.${kind}`)}
              />
            )}
            {/* What adding this kind actually does — the repository one is the
                reason this hint exists at all, since "add a repository" does
                not say by itself that nothing will touch your checkout. */}
            <p className="text-xs text-muted-foreground">{t(`workflow.inputs.hints.${kind}`)}</p>
          </div>

          {/* A note's title IS its label, so asking for both would be asking
              the same question twice. */}
          {kind === "note" ? null : (
            <div className="space-y-2">
              <Label htmlFor="input-description">{t("workflow.inputs.descriptionLabel")}</Label>
              <Input
                id="input-description"
                value={description}
                disabled={pending}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("workflow.inputs.descriptionPlaceholder")}
              />
            </div>
          )}

          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button disabled={incomplete || pending} onClick={submit}>
            {upload.isPending ? t("workflow.inputs.uploading") : t("workflow.inputs.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
