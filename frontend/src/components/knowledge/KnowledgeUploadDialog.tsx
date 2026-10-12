// frontend/src/components/knowledge/KnowledgeUploadDialog.tsx
//
// Upload documents into a collection (boards 5.1.26–5.1.28): Coffer converts
// each to Markdown and writes it as a source on the spot. Only the Markdown is
// kept, not the uploaded file. Files are dropped on the zone or chosen,
// several at once; each shows its name, kind and size, and the target
// collection shows before anything is sent. Upload sends them one after
// another, each with its own outcome on its row — converting, saved, or
// refused with what to do instead (a ZIP or anything over 20 MB before it is
// sent, a scanned PDF or an unsupported type once the daemon has looked at
// it); one file refused never stops the rest. When every file is saved the
// dialog closes with one toast; when some were refused it stays open on the
// outcomes, with a toast counting both. Cancel stays live while converting: it
// aborts the file being converted and sends no more.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeCollectionSelect } from "@/components/knowledge/KnowledgeCollectionSelect";
import {
  KnowledgeUploadRow,
  KnowledgeUploadZone,
  type UploadItem as Item,
} from "@/components/knowledge/KnowledgeUploadRow";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { refusalOf, refuseBeforeSending } from "@/lib/knowledge/uploadChecks";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  initial: string | null;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function KnowledgeUploadDialog({ open, onOpenChange, collections, initial }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const upload = useUploadKnowledgeFile();
  const input = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [collection, setCollection] = useState("");
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const aborter = useRef<AbortController | null>(null);
  const nextId = useRef(0);

  useEffect(() => {
    if (open) {
      setItems([]);
      setFinished(false);
      setRunning(false);
      setCollection(initial ?? collections[0]?.name ?? "");
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const add = (files: FileList | File[] | null | undefined) => {
    if (!files || files.length === 0) return;
    const added = Array.from(files).map((file): Item => {
      const early = refuseBeforeSending(t, file);
      return {
        id: nextId.current++,
        file,
        status: early ? "refused" : "ready",
        refusal: early,
      };
    });
    setFinished(false);
    setItems((current) => [...current, ...added]);
  };
  const remove = (id: number) => setItems((current) => current.filter((i) => i.id !== id));
  const patch = (id: number, next: Partial<Item>) =>
    setItems((current) => current.map((i) => (i.id === id ? { ...i, ...next } : i)));

  const ready = items.filter((i) => i.status === "ready");

  // One file after another; a refusal is that file's outcome, not the end.
  const send = async () => {
    if (ready.length === 0 || running) return;
    setRunning(true);
    const controller = new AbortController();
    aborter.current = controller;
    const saved: Item[] = [];
    let refused = 0;
    for (const item of ready) {
      if (controller.signal.aborted) return;
      patch(item.id, { status: "converting" });
      try {
        const doc = await upload.mutateAsync({
          collection,
          file: item.file,
          signal: controller.signal,
        });
        patch(item.id, { status: "saved", path: doc.path });
        saved.push({ ...item, path: doc.path });
      } catch (error) {
        if (controller.signal.aborted || isAbort(error)) return;
        refused += 1;
        patch(item.id, {
          status: "refused",
          refusal: refusalOf(t, error, item.file),
          retryable: true,
        });
      }
    }
    aborter.current = null;
    setRunning(false);
    const earlier = items.filter((i) => i.status === "refused").length;
    if (refused === 0 && earlier === 0) {
      toast.success(
        saved.length === 1
          ? t("knowledge.upload.written", { name: saved[0].file.name, path: saved[0].path })
          : t("knowledge.upload.allSaved", { count: saved.length, collection }),
      );
      onOpenChange(false);
      return;
    }
    setFinished(true);
    const failed = refused + earlier;
    if (saved.length > 0) {
      toast.success(t("knowledge.upload.someSaved", { count: saved.length, refused: failed }));
    } else {
      toast.error(t("knowledge.upload.noneSaved", { count: failed }));
    }
  };

  // Try again: the files the daemon refused go back in the queue.
  const retry = () =>
    setItems((current) =>
      current.map((i) =>
        i.retryable ? { ...i, status: "ready", refusal: null, retryable: false } : i,
      ),
    );
  const retryable = items.some((i) => i.retryable);

  // Cancel while converting abandons the file in flight and the rest;
  // otherwise it just closes.
  const cancel = () => {
    aborter.current?.abort();
    aborter.current = null;
    setRunning(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(next) : cancel())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("knowledge.upload.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.upload.body")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {items.length > 0 ? (
            <ul
              aria-label={t("knowledge.upload.files")}
              className="flex max-h-[280px] flex-col gap-2 overflow-auto"
            >
              {items.map((item) => (
                <KnowledgeUploadRow
                  key={item.id}
                  item={item}
                  removable={!running && item.status !== "saved"}
                  onRemove={() => remove(item.id)}
                />
              ))}
            </ul>
          ) : null}
          <KnowledgeUploadZone
            more={items.length > 0}
            disabled={running}
            onChoose={() => input.current?.click()}
            onFiles={add}
          />
          <input
            ref={input}
            type="file"
            multiple
            className="hidden"
            aria-label={t("knowledge.upload.choose")}
            onChange={(e) => {
              const chosen = e.target.files ? Array.from(e.target.files) : [];
              e.target.value = "";
              add(chosen);
            }}
          />
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-upload-collection" required>
              {t("knowledge.upload.into")}
            </Label>
            <KnowledgeCollectionSelect
              id="knowledge-upload-collection"
              collections={collections}
              value={collection}
              onChange={setCollection}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={cancel}>
            {finished && ready.length === 0 ? t("common.close") : t("common.cancel")}
          </Button>
          {finished && ready.length === 0 && retryable ? (
            <Button variant="outline" onClick={retry}>
              {t("common.tryAgain")}
            </Button>
          ) : null}
          {finished && ready.length === 0 ? null : (
            <Button
              onClick={() => void send()}
              disabled={ready.length === 0 || !collection || running}
            >
              {running
                ? t("knowledge.upload.uploading")
                : ready.length > 1
                  ? t("knowledge.upload.buttonMany", { count: ready.length })
                  : t("knowledge.upload.button")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
