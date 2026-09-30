// frontend/src/components/knowledge/KnowledgeChangeRow.tsx
//
// One change on the Recent changes timeline: who, what (in words, from the
// change's fields), which collection, when, and how many lines it moved. The
// row opens the change — for a curation pass, its diffs and Undo this pass.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { ChangeOut } from "@/lib/api/knowledge";
import { changeSentence, writerLabel } from "@/lib/knowledge/changes";
import { changePath } from "@/lib/knowledge/routes";
import { formatDateTime } from "@/lib/utils";

interface Props {
  change: ChangeOut;
  /** A later change undid this pass. */
  undone: boolean;
}

export function KnowledgeChangeRow({ change, undone }: Props) {
  const { t } = useTranslation();
  const added = change.documents.reduce((n, d) => n + d.added, 0);
  const removed = change.documents.reduce((n, d) => n + d.removed, 0);
  return (
    <li>
      <Link
        to={changePath(change.version)}
        className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-3 py-2 text-sm hover:bg-surface-hover"
      >
        <span className="font-medium">{writerLabel(t, change)}</span>
        <span className="min-w-0 flex-1 truncate text-text-muted">{changeSentence(t, change)}</span>
        {undone ? (
          <span className="rounded-sm bg-chip px-1.5 text-2xs text-text-muted">
            {t("knowledge.pass.undone")}
          </span>
        ) : null}
        <span className="text-xs tabular-nums text-text-subtle">
          {added > 0 ? <span className="text-success">+{added}</span> : null}{" "}
          {removed > 0 ? <span className="text-danger">−{removed}</span> : null}
        </span>
        <span className="w-full text-xs text-text-subtle">
          {change.collections.join(", ")} · {formatDateTime(change.time)}
        </span>
      </Link>
    </li>
  );
}
