// frontend/src/components/knowledge/KnowledgeAddBar.tsx
// One add-by-shape input for the unified 知识 surface (FR-017b): pasted text or
// a link becomes a NOTE (a memory fact) in the scope's store; a chosen / dropped
// file becomes a DOCUMENT (a KB upload) at the same scope. The shape of what you
// give it routes it — there is no kind picker beyond choosing the target KB when
// more than one exists. Writes go through the existing REST surfaces (the hook).
import { useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { FileUp, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { KnowledgeBaseOut } from "@/kinds/knowledge_base/api";

interface Props {
  /** KBs available as upload targets; empty disables file upload. */
  kbs: KnowledgeBaseOut[];
  /** True when the scope has a memory store (notes can be added). */
  canAddNote: boolean;
  isAddingNote: boolean;
  isUploading: boolean;
  onAddNote: (text: string) => void;
  onUploadFile: (kbName: string, file: File) => void;
}

export function KnowledgeAddBar({
  kbs,
  canAddNote,
  isAddingNote,
  isUploading,
  onAddNote,
  onUploadFile,
}: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [kbName, setKbName] = useState<string>(kbs[0]?.name ?? "");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const targetKb = kbs.find((k) => k.name === kbName)?.name ?? kbs[0]?.name ?? "";
  const canUpload = kbs.length > 0 && Boolean(targetKb);

  const submitNote = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onAddNote(trimmed);
    setText("");
  };

  const pickFiles = (files: FileList | null) => {
    if (!files || !canUpload) return;
    for (const file of Array.from(files)) onUploadFile(targetKb, file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    pickFiles(e.dataTransfer.files);
  };

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3",
        dragOver ? "border-primary ring-1 ring-primary/40" : "border-border",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        if (canUpload) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        disabled={!canAddNote}
        placeholder={t(canAddNote ? "knowledge.add.placeholder" : "knowledge.add.notesUnavailable")}
        className="resize-none border-0 bg-transparent px-1 shadow-none focus-visible:ring-0"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <FileUp className="size-3.5" />
          {canUpload ? t("knowledge.add.dropHint") : t("knowledge.add.uploadUnavailable")}
          {kbs.length > 1 ? (
            <Select value={targetKb} onValueChange={setKbName}>
              <SelectTrigger className="h-7 w-auto min-w-[8rem] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {kbs.map((kb) => (
                  <SelectItem key={kb.name} value={kb.name}>
                    {kb.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              pickFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!canUpload || isUploading}
            onClick={() => fileRef.current?.click()}
          >
            <FileUp className="mr-1.5 size-3.5" /> {t("knowledge.add.uploadFile")}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!canAddNote || isAddingNote || !text.trim()}
            onClick={submitNote}
          >
            <Plus className="mr-1.5 size-3.5" /> {t("knowledge.add.addNote")}
          </Button>
        </div>
      </div>
    </div>
  );
}
