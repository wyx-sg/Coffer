// frontend/src/components/skills/UnmanagedSkillFiles.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// The Files tab of an unmanaged skill's detail page: the same read-only Files
// card as a folder outside the library (SkillReadOnlyFiles), bound to the
// read-only routes under /agents/{uid}/unmanaged-skills/{name}/files.
//
// The viewer only reads. Coffer does not own these bytes until the folder is
// adopted, so there is no draft, no fingerprint and no save — Reveal in Finder
// and Open in editor are the honest way to change something another tool put
// there.
import { SkillReadOnlyFiles } from "@/components/skills/SkillReadOnlyFiles";
import {
  useUnmanagedSkillFileContent,
  useUnmanagedSkillFiles,
} from "@/lib/hooks/useUnmanagedSkill";

interface UnmanagedRef {
  agentUid: string;
  location: string;
  name: string;
}

export function UnmanagedSkillFiles({ agentUid, location, name }: UnmanagedRef) {
  const tree = useUnmanagedSkillFiles(agentUid, location, name);
  const useContent = (path: string) => useUnmanagedSkillFileContent(agentUid, location, name, path);
  return <SkillReadOnlyFiles name={name} tree={tree} useContent={useContent} />;
}
