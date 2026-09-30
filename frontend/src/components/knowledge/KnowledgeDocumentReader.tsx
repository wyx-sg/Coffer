// frontend/src/components/knowledge/KnowledgeDocumentReader.tsx
//
// The Document tab while reading (board 5.1.01): the rendered document in a
// reading column, and a quiet rail beside it — On this page (the document's
// own headings, each scrolling to itself), Properties (who edited it last and
// when, when it was created and by whom, how many curation passes it was
// curated from) and the file actions (open in the person's editor, reveal in
// their file manager, delete). Every document is the same here, whoever wrote
// it last (spec knowledge "Let only a person delete a document").
//
// When the newest version is a curation pass, a line above the body says so and
// links to what that pass changed — the answer to "why does this read
// differently than yesterday?".
import { useMemo, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowRight, ExternalLink, FolderOpen, Trash2 } from "lucide-react";

import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { FileOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/agents/hookRows";
import { agentLabel, writerLabel } from "@/lib/knowledge/changes";
import { changePath } from "@/lib/knowledge/routes";
import { outlineOf } from "@/lib/knowledge/text";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { cn } from "@/lib/utils";

interface Props {
  file: FileOut;
  onOpen: () => void;
  onReveal: () => void;
  onDelete: () => void;
}

export function KnowledgeDocumentReader({ file, onOpen, onReveal, onDelete }: Props) {
  const { t, i18n } = useTranslation();
  const history = useDocumentHistory(file.path);
  const bodyRef = useRef<HTMLDivElement>(null);
  const outline = useMemo(() => outlineOf(file.body), [file.body]);

  const versions = history.data?.versions ?? [];
  const newest = versions[0]?.change;
  const oldest = versions[versions.length - 1]?.change;
  const passes = versions.filter((v) => v.change.operation === "pass").length;
  const curatedLast = newest && newest.writer === "curation" && newest.operation === "pass";
  const top = outline.length ? Math.min(...outline.map((h) => h.level)) : 1;

  const scrollTo = (index: number) => {
    const nodes = bodyRef.current?.querySelectorAll("h2, h3, h4");
    const node = nodes?.[index];
    if (node && "scrollIntoView" in node) node.scrollIntoView({ block: "start" });
  };

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-border">
        <div className="flex min-h-0 flex-1 flex-col gap-[18px] px-10 pb-7 pt-[22px]">
          {curatedLast ? (
            <p className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-text-muted">
              <KnowledgeWriterMark writer="curation" />
              <span>
                {t("knowledge.document.curatedBanner", {
                  agent: agentLabel(t, newest.agent),
                  when: timeAgo(newest.time, i18n.language),
                })}
              </span>
              <Link
                to={changePath(newest.version)}
                className="inline-flex items-center gap-1 font-label text-text hover:underline"
              >
                {t("knowledge.document.seePass")}
                <ArrowRight className="size-3" aria-hidden />
              </Link>
            </p>
          ) : null}
          <div ref={bodyRef} className="flex min-h-0 max-w-[640px] flex-1 flex-col">
            <FindableMarkdown fill>{file.body}</FindableMarkdown>
          </div>
        </div>
      </div>

      <aside
        aria-label={t("knowledge.document.rail")}
        className="hidden w-[210px] shrink-0 flex-col gap-[22px] overflow-auto px-5 py-[22px] lg:flex"
      >
        {outline.length > 0 ? (
          <section className="flex flex-col gap-1.5">
            <h3 className="text-2xs font-semibold text-text-muted">
              {t("knowledge.document.onThisPage")}
            </h3>
            <div className="flex flex-col">
              {outline.map((h, i) => (
                <button
                  key={`${i}-${h.text}`}
                  type="button"
                  onClick={() => scrollTo(i)}
                  style={{ paddingLeft: (h.level - top) * 10 }}
                  className={cn(
                    "truncate py-[3px] text-left text-xs hover:text-text",
                    i === 0 ? "text-text" : "text-text-muted",
                  )}
                >
                  {h.text}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <section className="flex flex-col gap-1.5">
          <h3 className="text-2xs font-semibold text-text-muted">
            {t("knowledge.document.properties")}
          </h3>
          <dl className="flex flex-col">
            <Property label={t("knowledge.document.edited")}>
              <span className="flex min-w-0 items-center gap-1.5">
                {newest ? (
                  <KnowledgeWriterMark writer={newest.writer} agent={newest.agent} />
                ) : null}
                <span className="min-w-0">
                  {t("knowledge.document.byWhen", {
                    who: newest ? writerLabel(t, newest) : agentLabel(t, file.actor),
                    when: timeAgo(newest?.time ?? file.updated_at, i18n.language),
                  })}
                </span>
              </span>
            </Property>
            <Property label={t("knowledge.document.created")}>
              {t("knowledge.document.byWhen", {
                who: oldest ? writerLabel(t, oldest) : agentLabel(t, file.actor),
                when: new Date(file.created_at).toLocaleDateString(i18n.language, {
                  month: "short",
                  day: "numeric",
                }),
              })}
            </Property>
            {passes > 0 ? (
              <Property label={t("knowledge.document.curatedFrom")}>
                {t("knowledge.document.passes", { count: passes })}
              </Property>
            ) : null}
          </dl>
        </section>

        <section className="flex flex-col items-start gap-2">
          <RailAction icon={ExternalLink} label={t("fileActions.openInEditor")} onClick={onOpen} />
          <RailAction icon={FolderOpen} label={t("fileActions.reveal")} onClick={onReveal} />
          <RailAction
            icon={Trash2}
            label={t("knowledge.deleteDocument.menu")}
            onClick={onDelete}
            danger
          />
        </section>
      </aside>
    </div>
  );
}

function Property({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[62px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-[7px]">
      <dt className="text-xs text-text-subtle">{label}</dt>
      <dd className="min-w-0 break-words text-xs text-text">{children}</dd>
    </div>
  );
}

function RailAction({
  icon: Icon,
  label,
  onClick,
  danger,
}: {
  icon: typeof ExternalLink;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 text-xs font-label hover:underline",
        danger ? "text-danger" : "text-text-muted hover:text-text",
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {label}
    </button>
  );
}
