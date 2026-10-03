// frontend/src/components/files/ReadOnlyFile.tsx
//
// A file Coffer shows but does not own — an agent's memory file, an unmanaged
// skill's file, a skill folder outside the library: the viewer toolbar (path
// and size, Preview / Source for Markdown, a wrap toggle for code, Open in
// editor, optionally a Reveal icon) over the text. It only reads; changing the
// file is what the editor button is for. A binary file says it can't be
// previewed and offers Reveal in Finder; a file read only in part wears the
// grey bar over its start. `query` is the query's state, so a loading file or
// a failed read keeps the toolbar and says so below it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileBody } from "@/components/files/FileBody";
import { BinaryPane, TruncatedBar } from "@/components/files/FileStates";
import { isMarkdownPath } from "@/components/files/middlePath";
import { ViewerToolbar, type FileView } from "@/components/files/ViewerToolbar";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";

/** @ui-only What a read-only viewer needs of a file's content response. */
interface ReadOnlyContent {
  content: string;
  abs_path?: string;
  binary: boolean;
  size: number;
  truncated: boolean;
}

export interface ReadOnlyQuery {
  isPending: boolean;
  error: unknown;
  data: ReadOnlyContent | undefined;
  /** Retry a failed read; without it the error has no Retry. */
  refetch?: () => unknown;
}

export function ReadOnlyFile({
  path,
  displayPath,
  query,
  reveal,
}: {
  /** The file's name or relative path, which picks its language. */
  path: string;
  /** The path as the toolbar shows it. */
  displayPath: string;
  query: ReadOnlyQuery;
  reveal?: boolean;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const editor = usePreferredEditor();
  const [view, setView] = useState<FileView>("preview");
  const [wrap, setWrap] = useState(false);
  const data = query.data;
  const abs = data?.abs_path;
  const text = data && !data.binary;
  const markdown = isMarkdownPath(path) && !data?.truncated;

  return (
    <>
      <ViewerToolbar
        path={displayPath}
        absPath={abs}
        size={data?.size}
        reveal={reveal}
        view={text && markdown ? { value: view, onChange: setView } : undefined}
        wrap={text && !markdown ? { on: wrap, onChange: setWrap } : undefined}
      />
      {query.isPending ? (
        <div className="space-y-2 p-4" aria-busy="true">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : query.error || !data ? (
        <div className="p-4">
          <LoadErrorRow
            title={t("files.loadFailed")}
            error={query.error}
            onRetry={query.refetch ? () => void query.refetch?.() : undefined}
          />
        </div>
      ) : data.binary ? (
        <BinaryPane
          name={path.split("/").pop() ?? path}
          size={data.size}
          onReveal={
            abs
              ? () => void fs.reveal(abs).catch(() => toast.error(t("fileActions.revealFailed")))
              : undefined
          }
        />
      ) : (
        <>
          {data.truncated ? (
            <TruncatedBar
              shown={data.content.length}
              total={data.size}
              onOpenInEditor={
                abs
                  ? () =>
                      void fs
                        .open(abs, editor)
                        .catch(() => toast.error(t("fileActions.openFailed")))
                  : undefined
              }
            />
          ) : null}
          <FileBody
            path={path}
            text={data.content}
            view={view}
            wrap={wrap}
            truncated={data.truncated}
          />
        </>
      )}
    </>
  );
}
