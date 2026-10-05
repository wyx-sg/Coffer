// frontend/src/components/memory/MemoryPane.tsx — the selected memory, read-only.
//
// Its title, the meta line "Learned by Claude Code, Codex · updated <date>"
// taken from its provenance, and its body rendered as Markdown (spec memory
// "Show a partition's memories read-only"). The daemon hands the body without
// its frontmatter, so frontmatter never renders as text; the provenance is
// reduced to agent names — never a native path or an agent's original text.
// The body is a FindableMarkdown (⌘F find; `frontmatter={false}` because the
// daemon already stripped it). The page never edits a memory: MemoryViewActions
// offers Open in editor and a ⋯ menu with Reveal in Finder and Delete…, and a
// person changes the file in their own editor (spec memory "Edit a memory in
// the person's own editor"). Title 15/600, meta 12, body 13, 620 wide.
import { useTranslation } from "react-i18next";

import { learnedByLabels } from "@/components/memory/memoryAgents";
import { MemoryViewActions } from "@/components/memory/MemoryViewActions";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { NoteOut } from "@/lib/api/memoryTypes";
import { useMemoryNote } from "@/lib/hooks/useMemory";
import { formatDateTime } from "@/lib/utils";

interface Props {
  uid: string;
  slug: string;
}

export function MemoryPane({ uid, slug }: Props) {
  const { t } = useTranslation();
  const note = useMemoryNote(uid, slug);

  if (note.isPending) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (note.error || !note.data) {
    return (
      <p className="text-sm text-danger">
        {t("memory.memories.loadFailed")} {note.error ? translateApiError(t, note.error) : null}
      </p>
    );
  }
  return <LoadedMemory uid={uid} slug={slug} memory={note.data} />;
}

interface LoadedProps {
  uid: string;
  slug: string;
  memory: NoteOut;
}

function LoadedMemory({ uid, slug, memory: m }: LoadedProps) {
  const { t } = useTranslation();
  const agents = learnedByLabels(m.origins);
  const date = formatDateTime(m.updated_at);

  return (
    <article className="flex min-h-0 flex-1 flex-col gap-4" data-testid="memory-pane">
      <header className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h2 className="text-md font-semibold text-text">{m.title}</h2>
          <p className="text-xs text-text-muted" data-testid="memory-meta">
            {agents.length > 0
              ? t("memory.memories.learnedBy", { agents: agents.join(", "), date })
              : t("memory.memories.updated", { date })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <MemoryViewActions uid={uid} slug={slug} title={m.title} filePath={m.file_path} />
        </div>
      </header>
      <FindableMarkdown fill frontmatter={false} className="text-sm">
        {m.body}
      </FindableMarkdown>
    </article>
  );
}
