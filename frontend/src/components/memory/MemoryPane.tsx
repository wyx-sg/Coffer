// frontend/src/components/memory/MemoryPane.tsx — the selected memory, read-only.
//
// Its title, the meta line "Learned by Claude Code, Codex · updated <date>"
// taken from its provenance, and its body rendered as Markdown (spec memory
// "Present a partition as its memories"). The daemon hands the body without
// its frontmatter, so frontmatter never renders as text; the provenance is
// reduced to agent names — never a native path or an agent's original text.
// Open in editor and reveal act on the memory's own file under
// `~/.coffer/derived/memory/<partition>/notes/`. No edit or delete: the next distil
// pass would rewrite either.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_SCROLL } from "@/components/filePane";
import { Markdown } from "@/components/Markdown";
import { learnedByLabels } from "@/components/memory/memoryAgents";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useMemoryNote } from "@/lib/hooks/useMemory";
import { formatDateTime } from "@/lib/utils";

interface Props {
  uid: string;
  slug: string;
  /** Absolute path of the memory's file, once the partition's files are read. */
  filePath: string | null;
}

export function MemoryPane({ uid, slug, filePath }: Props) {
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

  const m = note.data;
  const agents = learnedByLabels(m.origins);
  const date = formatDateTime(m.updated_at);
  return (
    <article className="flex min-h-0 flex-1 flex-col gap-4" data-testid="memory-pane">
      <header className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h2 className="text-lg font-semibold text-text">{m.title}</h2>
          <p className="text-xs text-text-muted" data-testid="memory-meta">
            {agents.length > 0
              ? t("memory.memories.learnedBy", { agents: agents.join(", "), date })
              : t("memory.memories.updated", { date })}
          </p>
        </div>
        {filePath ? <FileActions filePath={filePath} /> : null}
      </header>
      <div className={FILE_PANE_SCROLL}>
        <div className="max-w-[620px]">
          <Markdown>{m.body}</Markdown>
        </div>
      </div>
    </article>
  );
}
