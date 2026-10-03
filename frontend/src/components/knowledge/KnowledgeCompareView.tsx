// frontend/src/components/knowledge/KnowledgeCompareView.tsx
//
// Compare, after a stale save (board 5.1.29, 0.6.05 conflict mode): not a
// dialog but the document pane's own view. Two radio cards — Keep my edit /
// Take the version on disk — and the diff under them follows the choice: what
// changes in the file if that side wins. The footer's primary says what it will
// do ("Save my edit" / "Use the disk version"); Back to editing leaves the
// draft as it was. The side that is not kept stays in the document's History.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { Button } from "@/components/ui/button";
import { diffLines } from "@/lib/knowledge/lineDiff";
import { cn } from "@/lib/utils";

type Choice = "mine" | "disk";

interface Props {
  /** The document's file name. */
  name: string;
  /** What the person typed. */
  mine: string;
  /** What the disk says now. */
  onDisk: string;
  /** "Unsaved · started today at 13:58". */
  mineMeta: string;
  /** "Curation · today at 14:05". */
  diskMeta: string;
  saving: boolean;
  onBack: () => void;
  onSaveMine: () => void;
  onUseDisk: () => void;
}

export function KnowledgeCompareView({
  name,
  mine,
  onDisk,
  mineMeta,
  diskMeta,
  saving,
  onBack,
  onSaveMine,
  onUseDisk,
}: Props) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState<Choice>("mine");
  // Keeping my edit changes the file from the disk's text to mine; taking the
  // disk's version changes my text to the disk's.
  const rows = useMemo(
    () => (choice === "mine" ? diffLines(onDisk, mine) : diffLines(mine, onDisk)),
    [choice, mine, onDisk],
  );
  const added = rows.filter((r) => r.kind === "add").length;
  const removed = rows.filter((r) => r.kind === "del").length;

  const cards: { value: Choice; label: string; meta: string }[] = [
    { value: "mine", label: t("knowledge.compare.keepMine"), meta: mineMeta },
    { value: "disk", label: t("knowledge.compare.keepDisk"), meta: diskMeta },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5 px-8 pb-4 pt-5">
      <div className="flex shrink-0 flex-col gap-1">
        <h2 className="text-md font-semibold">{t("knowledge.compare.title")}</h2>
        <p className="text-xs text-text-muted">{t("knowledge.compare.note")}</p>
      </div>
      <div
        role="radiogroup"
        aria-label={t("knowledge.compare.title")}
        className="flex shrink-0 gap-2"
      >
        {cards.map((c) => {
          const on = choice === c.value;
          return (
            <label
              key={c.value}
              className={cn(
                "flex min-w-0 flex-1 cursor-pointer items-start gap-2.5 rounded-lg border bg-surface-raised p-3",
                on ? "border-accent ring-1 ring-accent" : "border-border",
              )}
            >
              <input
                type="radio"
                name="knowledge-compare-choice"
                className="peer sr-only"
                checked={on}
                onChange={() => setChoice(c.value)}
              />
              <span
                aria-hidden
                className={cn(
                  "mt-px flex size-4 shrink-0 items-center justify-center rounded-full border",
                  on ? "border-transparent bg-accent" : "border-text-subtle bg-surface-raised",
                )}
              >
                {on ? <span className="size-1.5 rounded-full bg-surface-raised" /> : null}
              </span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-label">{c.label}</span>
                <span className="text-xs text-text-muted">{c.meta}</span>
              </span>
            </label>
          );
        })}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <div className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-xs font-medium">{name}</span>
          <span className="inline-flex h-5 items-center gap-1 rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
            <span className="font-mono font-medium">~</span>
            {t("knowledge.compare.modify")}
          </span>
          <span className="ml-auto inline-flex gap-1.5 font-mono text-2xs">
            <span className="text-success">+{added}</span>
            <span className="text-danger">−{removed}</span>
          </span>
        </div>
        <KnowledgeDiff rows={rows} className="min-h-0 flex-1" />
        <p className="shrink-0 text-xs text-text-muted">
          {choice === "mine"
            ? t("knowledge.compare.captionMine")
            : t("knowledge.compare.captionDisk")}
        </p>
      </div>
      <div className="flex shrink-0 justify-end gap-2">
        <Button variant="ghost" onClick={onBack} disabled={saving}>
          {t("knowledge.compare.back")}
        </Button>
        {choice === "mine" ? (
          <Button onClick={onSaveMine} disabled={saving}>
            {saving ? t("common.saving") : t("knowledge.compare.saveMine")}
          </Button>
        ) : (
          <Button onClick={onUseDisk} disabled={saving}>
            {t("knowledge.compare.useDisk")}
          </Button>
        )}
      </div>
    </div>
  );
}
