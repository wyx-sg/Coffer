// src/lib/hooks/useComposerAttachments.ts
// The composer's attached files: each is uploaded the moment it is added
// (POST /chat/attachments) and tracked as uploading → ready | failed, so the
// composer can show a chip per file and hold Send until every upload is done
// (spec chat "Attach files from the Chat page composer").
//
// Failures render inline on their chip, not as a toast: the chip is where the
// owner looks, and it must stay until they remove it.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { chatApi, type ChatAttachment } from "@/lib/api/chat";
import { translateApiError } from "@/lib/api/errors";

/** Mirrors the daemon's per-file ceiling, checked here so a file that cannot
 *  pass is refused before it is sent. The daemon still enforces it. */
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
/** Mirrors the daemon's per-message count. */
const MAX_ATTACHMENTS_PER_MESSAGE = 10;

interface DraftAttachment {
  /** Stable render key for the chip. */
  key: string;
  name: string;
  size: number;
  mime: string;
  status: "uploading" | "ready" | "failed";
  /** The stored upload once `ready`. */
  uploaded?: ChatAttachment;
  /** Why a `failed` upload failed, translated. */
  error?: string;
}

export interface ComposerAttachments {
  items: DraftAttachment[];
  add: (files: File[]) => void;
  /** Detach one chip, cancelling its upload if it is still running. */
  remove: (key: string) => void;
  /** Detach the given chips (every chip when omitted), cancelling their uploads. */
  clear: (keys?: string[]) => void;
  /** Put back finished uploads a refused message carried, as ready chips. */
  restore: (uploads: ChatAttachment[]) => void;
  /** Some upload is still in flight. */
  uploading: boolean;
  /** Some upload failed and is still attached. */
  failed: boolean;
  /** The finished uploads, in attach order. */
  ready: ChatAttachment[];
  /** Chip keys of `ready`, in the same order. */
  readyKeys: string[];
}

let draftSerial = 0;

const holdsSlot = (it: DraftAttachment) => it.status === "uploading" || it.status === "ready";

export function useComposerAttachments(): ComposerAttachments {
  const { t } = useTranslation();
  const [items, setItems] = useState<DraftAttachment[]>([]);
  // The latest items, readable inside `add` without waiting for a render
  // (several files arrive in one call). Kept in step by `update`.
  const itemsRef = useRef<DraftAttachment[]>([]);
  // One controller per upload still in flight, so removing its chip cancels it.
  const controllers = useRef(new Map<string, AbortController>());

  const update = useCallback((fn: (prev: DraftAttachment[]) => DraftAttachment[]) => {
    itemsRef.current = fn(itemsRef.current);
    setItems(itemsRef.current);
  }, []);

  const patch = useCallback(
    (key: string, next: Partial<DraftAttachment>) => {
      update((prev) => prev.map((it) => (it.key === key ? { ...it, ...next } : it)));
    },
    [update],
  );

  const add = useCallback(
    (files: File[]) => {
      const added: DraftAttachment[] = [];
      // Only live uploads and finished ones hold one of the message's slots;
      // a refused or failed chip is just a note to its owner.
      let taken = itemsRef.current.filter(holdsSlot).length;
      for (const file of files) {
        draftSerial += 1;
        const base = {
          key: `draft-${draftSerial}`,
          name: file.name || "attachment",
          size: file.size,
          mime: file.type,
        };
        let error: string | undefined;
        if (taken >= MAX_ATTACHMENTS_PER_MESSAGE) {
          error = t("chat.attachments.tooMany");
        } else if (file.size > MAX_ATTACHMENT_BYTES) {
          error = t("chat.attachments.tooLarge");
        }
        if (error) {
          added.push({ ...base, status: "failed", error });
          continue;
        }
        taken += 1;
        const item: DraftAttachment = { ...base, status: "uploading" };
        added.push(item);
        const controller = new AbortController();
        controllers.current.set(item.key, controller);
        chatApi.uploadAttachment(file, controller.signal).then(
          (uploaded) => {
            controllers.current.delete(item.key);
            patch(item.key, { status: "ready", uploaded, mime: uploaded.mime });
          },
          (err: unknown) => {
            controllers.current.delete(item.key);
            // Cancelled because its chip was removed: nothing to report.
            if (controller.signal.aborted) return;
            patch(item.key, { status: "failed", error: translateApiError(t, err) });
          },
        );
      }
      if (added.length === 0) return;
      update((prev) => [...prev, ...added]);
    },
    [patch, update, t],
  );

  const cancel = useCallback((key: string) => {
    controllers.current.get(key)?.abort();
    controllers.current.delete(key);
  }, []);

  const remove = useCallback(
    (key: string) => {
      cancel(key);
      update((prev) => prev.filter((it) => it.key !== key));
    },
    [cancel, update],
  );

  const clear = useCallback(
    (keys?: string[]) => {
      const drop = keys ? new Set(keys) : null;
      for (const it of itemsRef.current) if (!drop || drop.has(it.key)) cancel(it.key);
      update((prev) => (drop ? prev.filter((it) => !drop.has(it.key)) : []));
    },
    [cancel, update],
  );

  const restore = useCallback(
    (uploads: ChatAttachment[]) => {
      const held = new Set(itemsRef.current.map((it) => it.uploaded?.id));
      const back = uploads
        .filter((u) => !held.has(u.id))
        .map((u): DraftAttachment => {
          draftSerial += 1;
          const { filename: name, size, mime } = u;
          return { key: `draft-${draftSerial}`, name, size, mime, status: "ready", uploaded: u };
        });
      if (back.length > 0) update((prev) => [...prev, ...back]);
    },
    [update],
  );

  // Leaving the page cancels whatever is still uploading.
  useEffect(() => {
    const live = controllers.current;
    return () => {
      for (const controller of live.values()) controller.abort();
      live.clear();
    };
  }, []);

  return useMemo(() => {
    const done = items.filter((it) => it.status === "ready" && it.uploaded);
    return {
      items,
      add,
      remove,
      clear,
      restore,
      uploading: items.some((it) => it.status === "uploading"),
      failed: items.some((it) => it.status === "failed"),
      ready: done.map((it) => it.uploaded!),
      readyKeys: done.map((it) => it.key),
    };
  }, [items, add, remove, clear, restore]);
}
