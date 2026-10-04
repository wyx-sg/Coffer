// frontend/src/components/knowledge/KnowledgeChangeRow.tsx
//
// One change on the Recent changes timeline (boards 5.1.21–5.1.23): the
// writer's mark, who and what in words — "Codex edited `daemon/port.md`" — its
// time, and a line under it saying more where the change's fields allow. A
// change an earlier curation pass made keeps its curation label. A delete — a document or
// a whole collection — carries Restore, which puts back exactly what it
// removed as a new change by you; it is refused in place, on the row, when the
// path or the collection's name is taken again (spec knowledge "Restore a
// deleted collection or document from Recent changes").
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ChangeOut, CollectionOut } from "@/lib/api/knowledge";
import { feedTime, feedWords, isRestorableDelete, writerLabel } from "@/lib/knowledge/changes";
import { collectionOfPath, collectionPath, pathInCollection } from "@/lib/knowledge/routes";
import { useRestoreDeleted } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  change: ChangeOut;
  collections: CollectionOut[];
  /** A later change restored what this delete removed. */
  restored: boolean;
}

/** The line under a row, from the change's own fields. */
function detailOf(t: ReturnType<typeof useTranslation>["t"], change: ChangeOut): string | null {
  switch (change.operation) {
    case "delete":
      return t("knowledge.recent.detail.delete");
    case "remove":
      return t("knowledge.recent.detail.remove", { count: change.documents.length });
    case "restore":
      return t("knowledge.recent.detail.restore");
    case "sync": {
      const lines = change.documents.reduce((n, d) => n + d.added + d.removed, 0);
      return t("knowledge.recent.detail.sync", { count: lines });
    }
    default:
      return null;
  }
}

export function KnowledgeChangeRow({ change, collections, restored }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const restore = useRestoreDeleted();
  const { verb, document, collection: wholeCollection, more } = feedWords(t, change);
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));
  const docUid = document ? uidOf.get(collectionOfPath(document)) : undefined;
  const removed = change.documents.every((d) => d.status === "removed");
  const detail = detailOf(t, change);
  const collectionName = change.collections[0] ?? "";

  const docLabel = document ? pathInCollection(document) : null;
  const docLink =
    document && docUid && !removed ? (
      <Link
        to={collectionPath(docUid, "document", document)}
        className="min-w-0 truncate font-mono text-xs text-accent-text"
      >
        {docLabel}
      </Link>
    ) : document ? (
      <span className="min-w-0 truncate font-mono text-xs text-text">{docLabel}</span>
    ) : wholeCollection ? (
      <span className="min-w-0 truncate font-mono text-xs text-text">{wholeCollection}</span>
    ) : null;

  return (
    <li className="border-t border-border-subtle">
      <div className="flex gap-3 py-3">
        <span className="pt-px">
          <KnowledgeWriterMark writer={change.writer} agent={change.agent} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-baseline gap-1.5 text-sm">
            <span className="shrink-0 font-label">{writerLabel(t, change)}</span>
            <span className="shrink-0 text-text-muted">{verb}</span>
            {docLink}
            {more > 0 ? (
              <span className="shrink-0 text-xs text-text-muted">
                {t("knowledge.recent.more", { count: more })}
              </span>
            ) : null}
            <span className="ml-auto flex shrink-0 items-baseline gap-3">
              {isRestorableDelete(change) ? (
                restored ? (
                  <span className="text-xs text-text-muted">{t("knowledge.recent.restored")}</span>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={restore.isPending}
                    onClick={() =>
                      restore.mutate(change.version, {
                        onSuccess: () =>
                          toast.success(
                            t("knowledge.recent.restoredToast", {
                              name:
                                change.operation === "remove"
                                  ? collectionName
                                  : (docLabel ?? "").split("/").pop(),
                            }),
                          ),
                      })
                    }
                  >
                    {restore.isPending
                      ? t("knowledge.recent.restoring")
                      : t("knowledge.recent.restore")}
                  </Button>
                )
              ) : null}
              <span className="whitespace-nowrap text-xs text-text-muted">
                {feedTime(t, change.time, i18n.language)}
              </span>
            </span>
          </div>
          {detail ? <p className="mt-0.5 text-xs text-text-muted">{detail}</p> : null}
          {restore.error ? (
            <p role="alert" className="mt-1 text-xs text-danger">
              {translateApiError(t, restore.error)}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}
