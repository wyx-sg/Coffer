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
// A Confluence page already imported is refused; Replace sends it again as a
// new source that supersedes the older (spec knowledge "Import a Confluence
// page as a readable source with its attachments"). An import that left
// parts behind is saved, and the dialog stays open saying which.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeCollectionSelect } from "@/components/knowledge/KnowledgeCollectionSelect";
import {
  KnowledgeUploadButtons,
  KnowledgeUploadRow,
  KnowledgeUploadZone,
  type UploadItem as Item,
} from "@/components/knowledge/KnowledgeUploadRow";
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
import { ApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";
import {
  batchOutcome,
  partsLeft,
  refusalOf,
  refuseBeforeSending,
} from "@/lib/knowledge/uploadChecks";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  initial: string | null;
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";

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
    // Saved, but with parts left behind: the dialog stays open to say which.
    let partials = 0;
    for (const item of ready) {
      if (controller.signal.aborted) return;
      patch(item.id, { status: "converting" });
      try {
        const doc = await upload.mutateAsync({
          collection,
          file: item.file,
          replace: item.replace,
          signal: controller.signal,
        });
        const partial = partsLeft(doc.report);
        if (partial) partials += 1;
        patch(item.id, { status: "saved", path: doc.path, partial });
        saved.push({ ...item, path: doc.path });
      } catch (error) {
        if (controller.signal.aborted || isAbort(error)) return;
        refused += 1;
        const exists = error instanceof ApiError && error.code === "KNOWLEDGE_SOURCE_EXISTS";
        patch(item.id, {
          status: "refused",
          refusal: refusalOf(t, error, item.file),
          retryable: !exists,
          replaceable: exists,
        });
      }
    }
    aborter.current = null;
    setRunning(false);
    const earlier = items.filter((i) => i.status === "refused").length;
    if (refused === 0 && earlier === 0 && partials === 0) {
      toast.success(
        saved.length === 1
          ? t("knowledge.upload.written", { name: saved[0].file.name, path: saved[0].path })
          : t("knowledge.upload.allSaved", { count: saved.length, collection }),
      );
      onOpenChange(false);
      return;
    }
    setFinished(true);
    const outcome = batchOutcome(t, saved.length, refused + earlier);
    (outcome.ok ? toast.success : toast.error)(outcome.text);
  };

  // Try again puts the files the daemon refused back in the queue; Replace puts
  // a page already imported back, to replace its source.
  const requeue = (flag: "retryable" | "replaceable") =>
    setItems((current) =>
      current.map((i) =>
        i[flag]
          ? {
              ...i,
              status: "ready",
              refusal: null,
              retryable: false,
              replaceable: false,
              replace: flag === "replaceable",
            }
          : i,
      ),
    );

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
          <KnowledgeUploadButtons
            done={finished && ready.length === 0}
            running={running}
            ready={ready.length}
            canSend={ready.length > 0 && !!collection && !running}
            retryable={items.some((i) => i.retryable)}
            replaceable={items.some((i) => i.replaceable)}
            onCancel={cancel}
            onRequeue={requeue}
            onSend={() => void send()}
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
