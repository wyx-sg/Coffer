// frontend/src/components/skills/SkillFileTree.tsx
// A managed skill's Files tab (canvas 4.3.01, 4.3.12): the Files card
// (SkillFileSplit) with the skill's master folder in its tree and the read-only
// viewer (SkillFileViewer) beside it; the built-in skill's files each wear a
// lock, because Coffer rewrites that folder at every start.
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
  return (
    <SkillFileSplit
      name={owner}
      tree={tree}
      selected={selected}
      onSelect={select}
      folderPath={skills.data?.find((s) => s.uid === uid)?.master_path}
      lockTitle={builtin ? t("skills.files.lockBuiltin") : undefined}
      detail={<SkillFileViewer key={selected} uid={uid} owner={owner} path={selected} />}
    />
  );
}
