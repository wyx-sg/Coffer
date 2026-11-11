// frontend/src/components/knowledge/KnowledgeFileLine.tsx
//
// The one quiet line under an open file's title (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"), read from the
// file's frontmatter; a part with no data is left out. Every file: when it
// was created and by whom. A file Coffer wrote from an upload or an import
// adds where it came from and what the import could not keep
// (KnowledgeImportParts), and the file an upload came from: opened from here
// on the Mac that uploaded it, named with where it is on any other. Which
// other keys a file carries is its collection's own rules, so Coffer shows
// none of them here (ADR knowledge-collections-own-their-format).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { PartialImport, SourceOrigin } from "@/components/knowledge/KnowledgeImportParts";
import { useToast } from "@/components/ui/toast";
import { fsApi } from "@/lib/api/fs";
import type { FileOut } from "@/lib/api/knowledge";
import { agentLabel } from "@/lib/knowledge/changes";

interface Props {
  file: FileOut;
}

const LINK = "text-text underline decoration-border underline-offset-2 hover:decoration-text";

export function KnowledgeFileLine({ file }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const parts: ReactNode[] = [];

  // Created: the frontmatter's `created_at` and `actor` — nothing else records it.
  if (file.created_at && !Number.isNaN(Date.parse(file.created_at))) {
    const date = new Date(file.created_at).toLocaleDateString(i18n.language, {
      month: "short",
      day: "numeric",
    });
    const who = agentLabel(t, file.actor);
    parts.push(
      <span key="created">
        {t("knowledge.document.createdBy", {
          date,
          who: who === t("knowledge.writer.user") ? t("knowledge.document.you") : who,
        })}
      </span>,
    );
  }

  const origin = file.origin ?? {};
  if (origin.url) {
    parts.push(<SourceOrigin key="origin" origin={origin} />);
  }
  const report = file.import_report;
  if (report && report.complete === false) {
    parts.push(<PartialImport key="partial" report={report} />);
  }

  if (file.original) {
    const local = file.original_path;
    parts.push(
      local ? (
        <span key="original" className="inline-flex flex-wrap items-center gap-x-1">
          {t("knowledge.document.original")}
          <button
            type="button"
            className={LINK}
            onClick={() =>
              void fsApi
                .open(local)
                .catch(() => toast.error(t("knowledge.document.originalFailed")))
            }
          >
            {file.original}
          </button>
        </span>
      ) : (
        <span key="original" data-testid="original-elsewhere" className="text-text-subtle">
          {t("knowledge.document.originalElsewhere", { name: file.original })}
        </span>
      ),
    );
  }

  return (
    <p
      data-testid="file-line"
      className="mb-5 mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-muted"
    >
      {parts.map((part, i) => (
        <span key={i} className="inline-flex items-center gap-x-2">
          {i > 0 ? <span aria-hidden>·</span> : null}
          {part}
        </span>
      ))}
    </p>
  );
}
