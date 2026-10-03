// frontend/src/components/agents/UnmanagedSkillFiles.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// The Files tab of an unmanaged skill's detail page (board 2.1.58): the same
// read-only Files card as any skill folder Coffer does not own
// (SkillReadOnlyFiles — the shared file tree with a lock and Reveal in its
// header, beside the shared read-only viewer), bound to the routes under
// /agents/{uid}/unmanaged-skills/{name}/files. SKILL.md opens first; the
// toolbar names the file by its home-abbreviated path.
//
// The viewer only reads. Coffer does not own these bytes until the folder is
// adopted, so there is no draft, no fingerprint and no save — Open in editor is
// the honest way to change something another tool put there.
import { SkillReadOnlyFiles } from "@/components/skills/SkillReadOnlyFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import {
  useUnmanagedSkillFileContent,
  useUnmanagedSkillFiles,
} from "@/lib/hooks/useUnmanagedSkill";

interface Props {
  agentUid: string;
  location: string;
  name: string;
}

export function UnmanagedSkillFiles({ agentUid, location, name }: Props) {
  const tree = useUnmanagedSkillFiles(agentUid, location, name);
  const folder = tree.data?.abs_path;
  const useContent = (path: string) => useUnmanagedSkillFileContent(agentUid, location, name, path);
  return (
    <SkillReadOnlyFiles
      name={name}
      tree={tree}
      useContent={useContent}
      folderPath={folder}
      displayPath={(path, abs) => abbreviateHomePath(abs ?? `${folder ?? name}/${path}`)}
    />
  );
}
