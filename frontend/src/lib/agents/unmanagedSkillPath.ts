// frontend/src/lib/agents/unmanagedSkillPath.ts
// The URL of one unmanaged skill's detail page (router: agents/:uid/skills/
// unmanaged/:location/:name). An unmanaged folder has no uid, so it is named the
// way the scan names it — the agent's uid, the scan location, the folder name —
// each segment encoded on its own.
export function unmanagedSkillPath(agentUid: string, location: string, name: string): string {
  const enc = encodeURIComponent;
  return `/agents/${enc(agentUid)}/skills/unmanaged/${enc(location)}/${enc(name)}`;
}
