// frontend/src/components/knowledge/KnowledgeSummaryLine.tsx
//
// A collection's summary (spec knowledge "Show a collection as one tree of
// read-only documents in the web UI"): one muted line under its description —
// how many Markdown files it holds, its folder (the home directory as ~, with
// a copy button) and when it last changed — then a line naming the rules file
// its README declares (or the one found at its root) and its start page, each
// opening that file (spec knowledge "Let each collection declare its own
// rules"), and one line saying what Coffer does with it, so nobody has to
// guess what is kept, synced and tidied: it is kept in Coffer, synced to the
// person's other Macs, every change is in its history, and their agent tidies
// it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { BookOpen, Check, Copy, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";
import { whenLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
}

/** `/Users/me/.coffer/…` as `~/.coffer/…`: how the board writes the folder. */
function homeRelative(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/)/, "~");
}

/** A collection-relative path as a knowledge-root-relative one: `AGENTS.md`
 *  in `shopee` is `shopee/AGENTS.md`, `../shared/rules.md` is `shared/rules.md`. */
function rootRelative(collection: string, relpath: string): string {
  const parts: string[] = [collection];
  for (const part of relpath.split("/")) {
    if (part === "..") parts.pop();
    else if (part && part !== ".") parts.push(part);
  }
  return parts.join("/");
}

/** The rules file and the start page, each opening its file; null when the
 *  collection has neither. */
function KnowledgeRulesLine({ collection }: Props) {
  const { t } = useTranslation();
  if (!collection.rules_file && !collection.entry_file) return null;
  const open = (relpath: string) => (
    <Link
      to={collectionPath(collection.uid, rootRelative(collection.name, relpath))}
      className="font-mono text-text underline decoration-border underline-offset-2 hover:decoration-text"
    >
      {relpath}
    </Link>
  );
  return (
    <p
      className="flex items-start gap-1.5 text-xs leading-[1.5] text-text-muted"
      data-testid="knowledge-rules"
    >
      <BookOpen className="mt-px size-3.5 shrink-0 text-text-subtle" aria-hidden />
      <span className="flex flex-wrap items-center gap-x-1.5">
        {collection.rules_file ? (
          <span className="inline-flex items-center gap-x-1">
            {t("knowledge.summary.rules")} {open(collection.rules_file)}
          </span>
        ) : null}
        {collection.rules_file && collection.entry_file ? <span aria-hidden>·</span> : null}
        {collection.entry_file ? (
          <span className="inline-flex items-center gap-x-1">
            {t("knowledge.summary.start")} {open(collection.entry_file)}
          </span>
        ) : null}
      </span>
    </p>
  );
}

export function KnowledgeSummaryLine({ collection }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const copyFolder = () =>
    void navigator.clipboard.writeText(collection.folder_path).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => toast.error(t("knowledge.collection.copyFailed")),
    );

  const parts = [t("knowledge.summary.files", { count: collection.note_count })];

  return (
    <div className="flex flex-col gap-1.5" data-testid="knowledge-summary">
      <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-text-muted">
        <span>{parts.join(" · ")}</span>
        <span aria-hidden>·</span>
        <span className="flex min-w-0 items-center gap-0.5">
          <span className="truncate font-mono" title={collection.folder_path}>
            {homeRelative(collection.folder_path)}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-5 shrink-0 [&_svg]:size-3"
            aria-label={t("knowledge.collection.copyPath")}
            onClick={copyFolder}
          >
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          </Button>
        </span>
        {collection.updated_at ? (
          <>
            <span aria-hidden>·</span>
            <span>
              {t("knowledge.summary.updated", {
                when: whenLabel(t, collection.updated_at, i18n.language),
              })}
            </span>
          </>
        ) : null}
      </p>
      <KnowledgeRulesLine collection={collection} />
      <p className="flex items-start gap-1.5 text-xs leading-[1.5] text-text-muted">
        <ShieldCheck className="mt-px size-3.5 shrink-0 text-text-subtle" aria-hidden />
        <span>{t("knowledge.summary.managed")}</span>
      </p>
    </div>
  );
}
