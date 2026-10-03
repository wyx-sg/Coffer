// frontend/src/components/knowledge/KnowledgeStatsLine.tsx
//
// A collection's properties (board 5.1.10): hairline rows with a 140px label
// column — Documents · Inbox · Last curated · Folder. Inbox reads "N waiting"
// with a ghost Open Inbox button, or "Nothing" and no button; while a Curate
// now run is draining, Last curated reads "Curating · n of m" straight from the
// daemon's in-flight list. With Coffer's model not set nothing ever waits and
// nothing is curated, so the rows are Documents and Folder alone. No big
// numbers: a number is shown only where it is the data.
//
// "Last curated" is the newest curation pass in the collection's own history,
// the same timeline Recent changes reads. The folder path is shown with the
// home directory as ~ and a copy button.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/timeAgo";
import { collectionPath } from "@/lib/knowledge/routes";
import { curatingLabel } from "@/lib/knowledge/text";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";
import { useUpkeepRun } from "@/lib/hooks/useUpkeep";

interface Props {
  collection: CollectionOut;
  modelSet: boolean | undefined;
}

function Row({ label, first, children }: { label: string; first?: boolean; children: ReactNode }) {
  return (
    <div
      className={`grid min-h-10 grid-cols-[140px_minmax(0,1fr)] items-center gap-4 ${first ? "" : "border-t border-border-subtle"}`}
    >
      <span className="text-sm font-medium text-text">{label}</span>
      <span className="flex min-w-0 items-center gap-2 text-sm text-text">{children}</span>
    </div>
  );
}

/** `/Users/me/.coffer/…` as `~/.coffer/…`: how the board writes the folder. */
function homeRelative(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/)/, "~");
}

export function KnowledgeStatsLine({ collection, modelSet }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const run = useUpkeepRun("knowledge", collection.uid);
  const changes = useKnowledgeChanges(collection.name);
  const lastPass = changes.data?.changes.find(
    (c) => c.writer === "curation" && c.operation === "pass",
  );
  const [copied, setCopied] = useState(false);

  const copyFolder = () =>
    void navigator.clipboard.writeText(collection.folder_path).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => toast.error(t("knowledge.editor.copyFailed")),
    );

  return (
    <div className="flex flex-col" data-testid="knowledge-stats">
      <Row label={t("knowledge.stats.documents")} first>
        {collection.document_count}
      </Row>
      {modelSet ? (
        <>
          <Row label={t("knowledge.stats.inbox")}>
            {collection.pending_count > 0 ? (
              <>
                {t("knowledge.stats.waiting", { count: collection.pending_count })}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(collectionPath(collection.uid, "inbox"))}
                >
                  {t("knowledge.stats.openInbox")}
                </Button>
              </>
            ) : (
              t("knowledge.stats.nothing")
            )}
          </Row>
          <Row label={t("knowledge.stats.curated")}>
            {run
              ? curatingLabel(t, run)
              : lastPass
                ? timeAgo(lastPass.time, i18n.language)
                : t("knowledge.stats.never")}
          </Row>
        </>
      ) : null}
      <Row label={t("knowledge.stats.folder")}>
        <span className="truncate font-mono text-xs" title={collection.folder_path}>
          {homeRelative(collection.folder_path)}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          className="shrink-0"
          aria-label={t("knowledge.collection.copyPath")}
          onClick={copyFolder}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
      </Row>
    </div>
  );
}
