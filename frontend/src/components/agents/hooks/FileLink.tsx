// src/components/agents/hooks/FileLink.tsx — a hook's file, opened in the person's editor.
//
// The path is the hook file's real one. Choosing it asks the daemon to open it
// in the preferred editor (spec agent-registry "Open config files in an
// external editor or reveal them"); a plugin's hooks.json opens the same way.
import { abbreviateHomePath } from "@/lib/agents/display";
import { useFileActionItems } from "@/lib/fileActionItems";

export function FileLink({ path }: { path: string }) {
  const [open] = useFileActionItems(path);
  return (
    <button
      type="button"
      title={open.label}
      onClick={open.onClick}
      className="break-all text-left font-mono text-xs text-text-muted underline decoration-border underline-offset-2 hover:text-text hover:decoration-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      {abbreviateHomePath(path)}
    </button>
  );
}
