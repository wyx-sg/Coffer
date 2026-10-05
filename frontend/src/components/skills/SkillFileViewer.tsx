// frontend/src/components/skills/SkillFileViewer.tsx
// The right half of the Files tab card (canvas 4.3.01, 4.3.12–4.3.16;
// Foundations 0.6.03), read-only (spec web-ui "Lay out the Skills page as the
// canvas draws it": a skill file is read-only in the Files tab): the 40px
// toolbar — the file's path under the skill's name, its size, Open in editor
// and Reveal in Finder — over the file. A skill's files are changed in the
// person's own editor, so the viewer has no Edit, no Save and no unsaved state.
//
// It is the shared read-only viewer (ReadOnlyFile): SKILL.md and other Markdown
// open rendered with the front matter as a key / value block and a Preview /
// Source switch; code shows its text with line numbers and a wrap toggle; a
// binary file says it can't be previewed and offers Reveal in Finder; a file
// too large to read whole shows its start under a grey bar with Open in editor.
import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { useSkillFileContent } from "@/lib/hooks/useSkills";

interface Props {
  uid: string;
  /** The skill's name: the toolbar's path starts with it. */
  owner: string;
  path: string;
}

export function SkillFileViewer({ uid, owner, path }: Props) {
  const content = useSkillFileContent(uid, path);
  return <ReadOnlyFile path={path} displayPath={`${owner}/${path}`} query={content} reveal />;
}
