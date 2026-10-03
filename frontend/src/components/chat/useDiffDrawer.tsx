// src/components/chat/useDiffDrawer.tsx — which changed file's diff the thread
// shows in its drawer: the reply and the path. It resets when the conversation
// changes; `drawer` is the element to render (null while nothing is open).
import { useEffect, useState } from "react";

import { DiffDrawer } from "./DiffDrawer";

export function useDiffDrawer(conversationId: string) {
  const [openFile, setOpenFile] = useState<{ messageId: string; path: string } | null>(null);
  useEffect(() => setOpenFile(null), [conversationId]);
  const drawer = openFile ? (
    <DiffDrawer
      conversationId={conversationId}
      messageId={openFile.messageId}
      path={openFile.path}
      onPathChange={(path) => setOpenFile({ messageId: openFile.messageId, path })}
      onClose={() => setOpenFile(null)}
    />
  ) : null;
  return {
    openFile,
    open: (messageId: string, path: string) => setOpenFile({ messageId, path }),
    drawer,
  };
}
