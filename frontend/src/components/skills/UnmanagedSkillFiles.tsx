// frontend/src/components/skills/UnmanagedSkillFiles.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// The Files tab of an unmanaged skill's detail page: the same two-pane browser
// as a managed skill's (SkillFileBrowser), bound to the read-only routes under
// /agents/{uid}/unmanaged-skills/{name}/files.
//
// The viewer only reads. Coffer does not own these bytes until the folder is
// adopted, so there is no draft, no fingerprint and no save — the <FileActions>
// bar opens the file in the user's own editor, which is the honest way to change
// something another tool put there.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { SkillFileBrowser } from "@/components/skills/SkillFileTree";
import { translateApiError } from "@/lib/api/errors";
import {
  useUnmanagedSkillFileContent,
  useUnmanagedSkillFiles,
} from "@/lib/hooks/useUnmanagedSkill";

interface UnmanagedRef {
  agentUid: string;
  location: string;
  name: string;
}

export function UnmanagedSkillFiles(props: UnmanagedRef) {
  const tree = useUnmanagedSkillFiles(props.agentUid, props.location, props.name);
  return (
    <SkillFileBrowser
      tree={tree}
      renderFile={(path) => <UnmanagedSkillFileViewer {...props} path={path} />}
    />
  );
}

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

function UnmanagedSkillFileViewer({
  agentUid,
  location,
  name,
  path,
}: UnmanagedRef & { path: string }) {
  const { t } = useTranslation();
  const content = useUnmanagedSkillFileContent(agentUid, location, name, path);

  if (content.isPending) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  if (content.error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, content.error)}
      </p>
    );
  }

  const absPath = content.data?.abs_path;
  const header = (
    <div className="space-y-2">
      <span className="block truncate font-mono text-xs text-muted-foreground">{path}</span>
      {absPath ? <FileActions filePath={absPath} /> : null}
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className="space-y-2">
        {header}
        <div className="flex h-80 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
          {t("skills.files.binary", { size: content.data.size })}
        </div>
      </div>
    );
  }

  const text = content.data?.content ?? "";
  return (
    <div className="space-y-2">
      {header}
      {isMarkdown(path) ? (
        <FindableMarkdown className="max-h-[60vh] overflow-auto rounded-md border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} maxHeight="60vh" className="bg-background" />
      )}
      {content.data?.truncated ? (
        <p className="text-xs text-muted-foreground">{t("skills.files.truncated")}</p>
      ) : null}
    </div>
  );
}
