// frontend/src/components/skills/SkillFileTree.tsx
// A managed skill's Files tab (canvas 4.3.01, 4.3.12): the Files card
// (SkillFileSplit) with the skill's master folder in its tree and the editable
// viewer (SkillFileViewer) beside it. A file with unsaved edits wears a dot in
// the tree; the built-in skill's files are read-only, each wearing a lock.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SkillFileSplit } from "@/components/skills/SkillFileSplit";
import { useSelectedFile } from "@/components/skills/skillFileHelpers";
import { SkillFileViewer } from "@/components/skills/SkillFileViewer";
import { useSkillFiles, useSkills } from "@/lib/hooks/useSkills";

export function SkillFileTree({
  uid,
  owner,
  builtin = false,
}: {
  uid: string;
  owner: string;
  builtin?: boolean;
}) {
  const { t } = useTranslation();
  const tree = useSkillFiles(uid);
  const skills = useSkills();
  const { selected, select } = useSelectedFile();
  const [dirtyPath, setDirtyPath] = useState<string | null>(null);
  return (
    <SkillFileSplit
      name={owner}
      tree={tree}
      selected={selected}
      onSelect={select}
      dirtyPath={dirtyPath}
      folderPath={skills.data?.find((s) => s.uid === uid)?.master_path}
      lockTitle={builtin ? t("skills.files.lockBuiltin") : undefined}
      detail={
        <SkillFileViewer
          key={selected}
          uid={uid}
          owner={owner}
          path={selected}
          builtin={builtin}
          onDirtyChange={(dirty) => setDirtyPath(dirty ? selected : null)}
        />
      }
    />
  );
}
