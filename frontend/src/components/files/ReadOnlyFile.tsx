// frontend/src/components/files/ReadOnlyFile.tsx
//
// A file Coffer shows but does not own — an agent's memory file, an unmanaged
// skill's file: the viewer toolbar (path, Preview / Source for Markdown, Open
// in editor, optionally a Reveal icon) over the text. It only reads; changing
// the file is what the editor button is for. `status` is the query's state, so
// a loading file or a failed read keeps the toolbar and says so below it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileBody } from "@/components/files/FileBody";
import { isMarkdownPath } from "@/components/files/middlePath";
import { ViewerToolbar, type FileView } from "@/components/files/ViewerToolbar";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes } from "@/lib/utils";

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
  refetch: () => unknown;
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
  const [view, setView] = useState<FileView>("preview");
  const data = query.data;
  const markdown = isMarkdownPath(path) && !data?.binary && !data?.truncated;

  return (
    <>
      <ViewerToolbar
        path={displayPath}
        absPath={data?.abs_path}
        reveal={reveal}
        view={markdown ? { value: view, onChange: setView } : undefined}
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
            onRetry={() => void query.refetch()}
          />
        </div>
      ) : data.binary ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
          <p className="text-sm font-label text-text">
            {t("files.binaryTitle", { size: formatBytes(data.size) })}
          </p>
          <p className="text-xs text-text-muted">{t("files.binaryBody")}</p>
        </div>
      ) : (
        <FileBody path={path} text={data.content} view={view} truncated={data.truncated} />
      )}
    </>
  );
}
