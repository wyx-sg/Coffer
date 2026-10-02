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
import { ReadOnlyFileView } from "@/components/skills/ReadOnlyFileView";
import { SkillFileBrowser } from "@/components/skills/SkillFileTree";
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

function UnmanagedSkillFileViewer({
  agentUid,
  location,
  name,
  path,
}: UnmanagedRef & { path: string }) {
  const content = useUnmanagedSkillFileContent(agentUid, location, name, path);
  return <ReadOnlyFileView path={path} content={content} />;
}
