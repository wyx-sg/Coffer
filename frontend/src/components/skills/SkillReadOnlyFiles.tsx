// frontend/src/components/skills/SkillReadOnlyFiles.tsx
// The read-only "tree + reader" for a skill folder Coffer does not own — the
// same Files card as a managed skill's (SkillFileSplit: tree with its header,
// the open file in `?file=`) with every file locked and the reader
// (ReadOnlyFileView) beside it. The unmanaged skill's Files tab and the pane of
// a folder that is not in the library both render this one component; each
// supplies the tree it read and how to read one file's content:
//
//   <SkillReadOnlyFiles name tree useContent={(path) => query} />
//
// `useContent` is a hook called for the open file, so it can be any React Query
// hook returning { isPending, error, data }.
import { useTranslation } from "react-i18next";

import { ReadOnlyFileView, type FileContentQuery } from "@/components/skills/ReadOnlyFileView";
import { SkillFileSplit, type SkillFileTreeQuery } from "@/components/skills/SkillFileSplit";
import { useSelectedFile } from "@/components/skills/skillFileHelpers";

interface Props {
  /** The folder's name, over the tree and in each file's path. */
  name: string;
  tree: SkillFileTreeQuery;
  /** Reads one file of the folder. */
  useContent: (path: string) => FileContentQuery;
  /** The folder's absolute path, for Reveal in Finder (the tree's own when absent). */
  folderPath?: string | null;
  /** The lock's reason; defaults to "Not in your library — read-only". */
  lockTitle?: string;
}

function OpenFile({
  name,
  path,
  useContent,
}: {
  name: string;
  path: string;
  useContent: Props["useContent"];
}) {
  const content = useContent(path);
  return <ReadOnlyFileView owner={name} path={path} content={content} />;
}

export function SkillReadOnlyFiles({ name, tree, useContent, folderPath, lockTitle }: Props) {
  const { t } = useTranslation();
  const { selected, select } = useSelectedFile();
  return (
    <SkillFileSplit
      name={name}
      tree={tree}
      selected={selected}
      onSelect={select}
      folderPath={folderPath}
      lockTitle={lockTitle ?? t("skills.files.lockNotMine")}
      detail={
        <div key={selected} className="flex min-h-0 flex-1 flex-col">
          <OpenFile name={name} path={selected} useContent={useContent} />
        </div>
      }
    />
  );
}
