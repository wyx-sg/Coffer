// frontend/src/components/memory/MemoryEditDialog.tsx
//
// A person's edit of one memory file (spec memory "Show and edit memory on the
// Memory page"): the whole file, frontmatter included, in one text area. Save
// writes it as one change in the vault's history, quoting the digest the file
// was read at, so an agent's write in between is refused rather than lost.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import type { MemoryFile } from "@/lib/api/memoryTypes";
import { useSaveMemoryFile } from "@/lib/hooks/useMemory";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  file: MemoryFile;
}

function Form({ file, onOpenChange }: Omit<Props, "open">) {
  const { t } = useTranslation();
  const save = useSaveMemoryFile();
  const [text, setText] = useState(file.text);

  return (
    <form
      className="flex min-h-0 flex-col gap-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (save.isPending) return;
        save.mutate(
          { project: file.project, name: file.name, text, expected: file.digest },
          { onSuccess: () => onOpenChange(false) },
        );
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("memory.edit.title", { name: file.name })}</DialogTitle>
        <DialogDescription>{t("memory.edit.body")}</DialogDescription>
      </DialogHeader>
      <Textarea
        aria-label={file.name}
        className="min-h-[320px] font-mono text-xs"
        value={text}
        autoFocus
        onChange={(e) => {
          setText(e.target.value);
          if (save.error) save.reset();
        }}
      />
      {save.error ? (
        <Alert variant="error">
          <CircleAlert aria-hidden />
          <AlertTitle>{t("memory.edit.failed", { name: file.name })}</AlertTitle>
          <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
        </Alert>
      ) : null}
      <DialogFooter className="mt-0">
        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={save.isPending || text === file.text}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function MemoryEditDialog({ open, onOpenChange, file }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[720px] grid-rows-[minmax(0,1fr)]">
        {open ? <Form file={file} onOpenChange={onOpenChange} /> : null}
      </DialogContent>
    </Dialog>
  );
}
