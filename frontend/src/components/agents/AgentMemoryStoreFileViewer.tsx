// frontend/src/components/agents/AgentMemoryStoreFileViewer.tsx — spec agent-registry
// "Read one native memory store's files read-only".
//
// The viewer beside the memory store's tree (boards 2.1.51, 2.1.61): the shared
// viewer toolbar — the file's path shortened in the middle, Preview / Source
// for Markdown, Open in editor — over the text. Markdown shows its front
// matter as a key / value grid and its body rendered; anything else is raw.
// A file too big shows its start and says so.
//
// It only reads. These files belong to the coding agent, which rewrites them
// whenever it learns something, so an in-app edit would be silently reverted
// by the agent's next pass. Opening the file in a real editor is the honest way
// to change something another process owns — hence no draft and no save.
import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useNativeMemoryFileContent } from "@/lib/hooks/useAgentNativeMemory";

export function AgentMemoryStoreFileViewer({
  agentUid,
  dir,
  path,
}: {
  agentUid: string;
  dir: string;
  path: string;
}) {
  const content = useNativeMemoryFileContent(agentUid, dir, path);
  const shown = abbreviateHomePath(content.data?.abs_path ?? `${dir.replace(/\/+$/, "")}/${path}`);
  return <ReadOnlyFile path={path} displayPath={shown} query={content} />;
}
