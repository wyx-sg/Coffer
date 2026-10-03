// components/chat/ThreadAttachment.tsx
// One attachment of a user message in the thread: an image whose bytes the
// daemon still holds shows as a thumbnail, anything else (a document, a channel
// file, a reference saved before ids existed, an image since pruned) as the chip
// naming it with its type — and its size where the reference carries one.
import { useEffect, useState } from "react";
import { chatApi, type ContentBlock } from "@/lib/api/chat";
import { formatBytes } from "@/lib/utils";
import { AttachmentChip } from "./AttachmentChip";

interface Props {
  conversationId: string;
  block: ContentBlock;
}

/** The object URL of an image's bytes, fetched with the token a plain <img src>
 *  cannot send; undefined while loading and when the file is gone (pruned), so
 *  the chip stays. Revoked when it changes or the component goes. */
function useImageUrl(conversationId: string, id: string | null, wanted: boolean) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!wanted || id === null) return;
    let objectUrl: string | undefined;
    let cancelled = false;
    chatApi
      .attachmentBlob(conversationId, id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(undefined);
    };
  }, [conversationId, id, wanted]);
  return url;
}

export function ThreadAttachment({ conversationId, block }: Props) {
  const id = block.attachment_id ?? null;
  const isImage = Boolean(block.mime?.startsWith("image/"));
  const src = useImageUrl(conversationId, id, isImage);
  const detail = [block.mime, block.size != null ? formatBytes(block.size) : null]
    .filter(Boolean)
    .join(" · ");
  return <AttachmentChip name={block.filename} detail={detail} mime={block.mime} src={src} />;
}
