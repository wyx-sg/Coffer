// frontend/src/components/knowledge/KnowledgeStatsLine.tsx
//
// A collection's properties (board 5.1.10): hairline rows with a 140px label
// column — Documents · Folder. No big numbers: a number is shown only where it
// is the data. The folder path is shown with the home directory as ~ and a
// copy button.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";

interface Props {
  collection: CollectionOut;
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

export function KnowledgeStatsLine({ collection }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
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
