// frontend/src/components/skills/ReadOnlyFileView.tsx — the file pane of a skill
// folder Coffer does not own (an unmanaged skill, a folder not in the library,
// a skill a plugin provides).
//
// Laid out like a managed skill's file pane (SkillFileViewer, canvas 4.3.12): the
// 40px toolbar — the path and size, a wrap toggle for code, a Preview / Source
// switch for Markdown — over the file, with no Edit: Coffer does not own these
// bytes, so there is no draft, no fingerprint and no save; changing one goes
// through the person's own editor (Open in editor on a truncated file, Reveal in
// Finder on a binary one).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  BinaryPane,
  FileBar,
  FileBody,
  TruncatedBar,
  ViewSwitch,
  WrapToggle,
} from "@/components/skills/SkillFilePanes";
import { isMarkdown, type FileView } from "@/components/skills/skillFileHelpers";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";

export interface FileContentQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileContentOut | undefined;
}

export function ReadOnlyFileView({
  path,
  content,
  owner,
}: {
  path: string;
  content: FileContentQuery;
  /** The folder's name: the toolbar's path starts with it, as a managed skill's does. */
  owner?: string;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const editor = usePreferredEditor();
  const [view, setView] = useState<FileView>("preview");
  const [wrap, setWrap] = useState(false);
  const shown = owner ? `${owner}/${path}` : path;

  if (content.isPending) {
    return (
      <>
        <FileBar path={shown} />
        <div className="space-y-2 p-4" aria-busy="true">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      </>
    );
  }
  const data = content.data;
  if (content.error || !data) {
    return (
      <>
        <FileBar path={shown} />
        <p className="p-4 text-sm text-danger" role="alert">
          {translateApiError(t, content.error)}
        </p>
      </>
    );
  }

  const abs = data.abs_path;
  const markdown = isMarkdown(path) && !data.truncated;
  if (data.binary) {
    return (
      <>
        <FileBar path={shown} size={data.size} />
        <BinaryPane
          name={path.split("/").pop() ?? path}
          size={data.size}
          onReveal={() =>
            abs && void fs.reveal(abs).catch(() => toast.error(t("fileActions.revealFailed")))
          }
        />
      </>
    );
  }

  return (
    <>
      <FileBar path={shown} size={data.size}>
        {markdown ? (
          <ViewSwitch value={view} onChange={setView} />
        ) : (
          <WrapToggle on={wrap} onChange={setWrap} />
        )}
      </FileBar>
      {data.truncated ? (
        <TruncatedBar
          shown={data.content.length}
          total={data.size}
          onOpenInEditor={() =>
            abs && void fs.open(abs, editor).catch(() => toast.error(t("fileActions.openFailed")))
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
  );
}
