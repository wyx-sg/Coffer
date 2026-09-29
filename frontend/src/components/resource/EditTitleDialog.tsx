// src/components/resource/EditTitleDialog.tsx
// The edit form of a kind whose only user-editable label is its title — a skill,
// whose name is fixed, and the kinds whose page has no other edit form. It sets,
// changes and clears the title through the kind-agnostic update; for a fixed
// name it shows the name read-only with the note saying why.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useSetResourceTitle } from "@/lib/hooks/useResourceMutations";
import { titlePatchValue, type Titled } from "@/lib/resourceTitle";
import { FixedNameField } from "./FixedName";
import { ResourceTitleField } from "./ResourceTitleField";

interface Props {
  kind: string;
  resource: Titled & { uid: string };
  /** Set for a kind whose name is fixed: what agents use the name for. The
   *  form then shows the name read-only with this note. */
  fixedNameHint?: string;
}

export function EditTitleDialog({ kind, resource, fixedNameHint }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const save = useSetResourceTitle();

  const onSave = () =>
    save.mutate(
      { kind, uid: resource.uid, title: titlePatchValue(title) },
      { onSuccess: () => setOpen(false) },
    );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setTitle(resource.title ?? "");
          save.reset();
        }
        setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Pencil className="mr-1.5 size-3.5" /> {t("resources.titleField.dialogTitle")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("resources.titleField.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("resources.titleField.dialogSubtitle")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            onSave();
          }}
        >
          {fixedNameHint ? (
            <FixedNameField id="edit-title-name" name={resource.name} hint={fixedNameHint} />
          ) : null}
          <ResourceTitleField
            id="edit-title"
            value={title}
            onChange={setTitle}
            name={resource.name}
            disabled={save.isPending}
          />
          {save.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, save.error)}
            </p>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
              disabled={save.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
