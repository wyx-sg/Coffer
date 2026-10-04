// frontend/src/components/skills/SkillNotOursNotice.tsx
// The refusal block of a delete (canvas 4.3.55, 4.3.39): an agent's folder is a
// regular folder now, not Coffer's link, and Coffer only removes what it made.
// Shared by the single and the bulk delete dialog.
import { AlertTriangle } from "lucide-react";

import { abbreviateHomePath } from "@/lib/agents/display";

interface Props {
  title: string;
  /** The text before the folder when something was deleted already (bulk). */
  lead?: string;
  path: string;
  /** What follows the folder: why Coffer won't remove it, and what to do. */
  tail: string;
}

export function NotOursNotice({ title, lead, path, tail }: Props) {
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5">
      <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 stroke-[1.75] text-danger" />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="break-words text-xs leading-[1.45] text-text-muted">
          {lead ? `${lead} ` : null}
          <code className="font-mono text-text">{abbreviateHomePath(path)}</code> {tail}
        </span>
      </div>
    </div>
  );
}
