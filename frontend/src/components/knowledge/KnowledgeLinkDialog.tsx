// frontend/src/components/knowledge/KnowledgeLinkDialog.tsx
// Link an external folder (ADR linked-knowledge-folders-are-read-only-and-machine-local):
// a folder the person keeps with their own tools, an Obsidian vault say, is
// shared with every agent and never copied into Coffer. The dialog says so
// before anything is linked: the files stay where they are, Coffer does not
// tidy, sync or keep history for them, and the folder's own rules apply. The
// name defaults to the folder's own and is only a label. A refusal (no such
// folder, already linked, a name taken) shows under the field it concerns.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Folder, Info } from "lucide-react";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
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
import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useLinkFolder } from "@/lib/hooks/useKnowledge";
import { collectionPath } from "@/lib/knowledge/routes";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function baseName(path: string): string {
  return (
    path
      .replace(/[/\\]+$/, "")
      .split(/[/\\]/)
      .pop() ?? ""
  );
}

export function KnowledgeLinkDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const link = useLinkFolder();
  const { toast } = useToast();
  const [folder, setFolder] = useState("");
  const [name, setName] = useState("");
  const [named, setNamed] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (open) {
      setFolder("");
      setName("");
      setNamed(false);
      setError(null);
    }
  }, [open]);

  const pick = (next: string | null) => {
    const path = next ?? "";
    setFolder(path);
    setError(null);
    if (!named) setName(baseName(path));
  };

  const nameTaken = error instanceof ApiError && error.code === "KNOWLEDGE_COLLECTION_EXISTS";

  const submit = () =>
    link.mutate(
      { folder: folder.trim(), name: name.trim() || null },
      {
        onSuccess: (linked) => {
          onOpenChange(false);
          toast.success(t("knowledge.linkFolder.linked", { name: linked.name }));
          navigate(collectionPath(linked.uid));
        },
        onError: setError,
      },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("knowledge.linkFolder.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.linkFolder.body")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-link-folder" required>
              {t("knowledge.linkFolder.folder")}
            </Label>
            <FolderPickerField
              inputId="knowledge-link-folder"
              ariaLabel={t("knowledge.linkFolder.folder")}
              value={folder || null}
              onChange={pick}
              placeholder={t("knowledge.linkFolder.folderHint")}
              typeable
              icon={<Folder aria-hidden className="size-3.5" />}
              invalid={Boolean(error) && !nameTaken}
            />
            {error && !nameTaken ? (
              <p role="alert" className="text-xs text-danger">
                {translateApiError(t, error)}
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-link-name" required>
              {t("knowledge.linkFolder.name")}
            </Label>
            <Input
              id="knowledge-link-name"
              value={name}
              aria-invalid={nameTaken || undefined}
              onChange={(e) => {
                setName(e.target.value);
                setNamed(true);
                setError(null);
              }}
            />
            {nameTaken ? (
              <p role="alert" className="text-xs text-danger">
                {translateApiError(t, error)}
              </p>
            ) : (
              <p className="text-xs text-text-muted">{t("knowledge.linkFolder.nameHint")}</p>
            )}
          </div>
          <div
            role="note"
            className="flex gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3 text-xs text-text-muted"
          >
            <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
            <ul className="space-y-1">
              <li>{t("knowledge.linkFolder.stays")}</li>
              <li>{t("knowledge.linkFolder.notManaged")}</li>
              <li>{t("knowledge.linkFolder.ownRules")}</li>
            </ul>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!folder.trim() || !name.trim() || link.isPending}>
            {t("knowledge.linkFolder.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
