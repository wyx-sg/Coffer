// frontend/src/components/workflow/NoteEditor.tsx — writing a note, including
// the screenshot you pasted into it.
//
// The paste is the reason this is its own component. A textarea with a paste
// handler is nearly the whole feature: a clipboard image goes to the run's own
// inputs as an ordinary upload, and what lands in the text is a markdown
// reference to it by name. Nothing about the note is special on disk, which is
// why a task reads it with the filesystem it already has.
//
// The upload happens before the text changes. A reference inserted first and
// an upload that then failed would leave the developer with markdown pointing
// at nothing, and they would find out when a task did.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ImagePlus } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { useUploadWorkflowInput } from "@/lib/hooks/useWorkflowInputs";

interface Props {
  runId: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
}

export function NoteEditor({ runId, value, onChange, disabled = false }: Props) {
  const { t } = useTranslation();
  const upload = useUploadWorkflowInput(runId);
  const box = useRef<HTMLTextAreaElement>(null);
  const [pasting, setPasting] = useState(false);

  const insert = (markdown: string) => {
    // Read the box rather than the prop: the upload takes as long as it takes
    // and the developer keeps typing, so `value` as this closure captured it
    // is the note as it was before the paste, and writing it back would undo
    // everything typed since.
    const current = box.current?.value ?? value;
    const at = box.current?.selectionStart ?? current.length;
    onChange(`${current.slice(0, at)}${markdown}${current.slice(at)}`);
  };

  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const image = [...event.clipboardData.items].find((item) => item.type.startsWith("image/"));
    if (image === undefined) return;
    const file = image.getAsFile();
    if (file === null) return;
    // Only now: letting the paste through as well would put the image's own
    // textual representation in the note beside the reference to it.
    event.preventDefault();
    setPasting(true);
    upload.mutate(
      { file: named(file), label: null },
      {
        onSuccess: (list) => {
          const added = list.items[list.items.length - 1];
          // Blank lines either side: pasted into the middle of a paragraph,
          // an image that touches the text around it is part of that
          // paragraph, and the heading under it stops being a heading.
          insert(`\n\n![${added.ref}](${added.ref})\n\n`);
        },
        onSettled: () => setPasting(false),
      },
    );
  };

  return (
    <div className="space-y-2">
      <Textarea
        ref={box}
        aria-label={t("workflow.notes.editorLabel")}
        className="min-h-[24rem] font-mono text-sm"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onPaste={onPaste}
        placeholder={t("workflow.notes.placeholder")}
      />
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ImagePlus className="size-3.5" aria-hidden />
        {pasting ? t("workflow.notes.pasting") : t("workflow.notes.pasteHint")}
      </p>
    </div>
  );
}

/**
 * A name for a pasted image. The clipboard gives one called `image.png` for
 * every paste, and the store would then number them `image-2.png`,
 * `image-3.png` — true, but useless in a note six screenshots long.
 */
function named(file: File): File {
  const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
  const extension = file.type.split("/")[1]?.replace("+xml", "") ?? "png";
  return new File([file], `pasted-${stamp}.${extension}`, { type: file.type });
}
