// src/components/change-preview/ChangePreviewBody.tsx
// The body of the change preview for each state: computing, empty, ready (targets + diffs), applying, applied, failed.
import { useRef, useState, type ReactNode } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ChangeSummary } from "./ChangeSummary";
import { ChangeTargetList } from "./ChangeTargetList";
import { FileDiff } from "./FileDiff";
import { WhatWillHappen } from "./WhatWillHappen";
import type {
  ChangeItem,
  ChangePreviewState,
  ChangeSummaryLine,
} from "@/lib/changePreview/changeCounts";

const SKELETON_WIDTHS = ["w-[70%]", "w-[48%]", "w-[62%]", "w-[40%]"];

function Computing() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <div className="flex items-center gap-2">
        <Loader2
          aria-hidden
          className="size-3.5 shrink-0 animate-spin text-text-subtle motion-reduce:animate-none"
        />
        <span role="status" className="text-sm text-text-muted">
          {t("changePreview.computing")}
        </span>
      </div>
      <div className="flex flex-col gap-3">
        {SKELETON_WIDTHS.map((width) => (
          <Skeleton key={width} className={`h-2.5 ${width}`} />
        ))}
      </div>
    </div>
  );
}

function Empty() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 py-[18px]">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
        <Check aria-hidden className="size-4 stroke-[2.5]" />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{t("changePreview.empty.title")}</span>
        <span className="text-xs text-text-muted">{t("changePreview.empty.body")}</span>
      </div>
    </div>
  );
}

function Review({
  items,
  summaries,
  lead,
  diffNote,
}: {
  items: readonly ChangeItem[];
  summaries: readonly ChangeSummaryLine[];
  lead?: ReactNode;
  diffNote?: string;
}) {
  const { t } = useTranslation();
  const diffs = items.filter((item) => item.diff && item.diff.length > 0);
  const [selectedId, setSelectedId] = useState<string | undefined>(diffs[0]?.id);
  const refs = useRef(new Map<string, HTMLElement>());
  const select = (id: string) => {
    setSelectedId(id);
    refs.current.get(id)?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  };
  return (
    <>
      <ChangeSummary items={items} />
      <div className="grid grid-cols-[330px_minmax(0,1fr)] items-start gap-5">
        <div className="flex min-w-0 flex-col gap-3">
          {lead}
          <WhatWillHappen summaries={summaries} />
          <section className="flex flex-col gap-1">
            <h3 className="text-2xs font-semibold text-text-subtle">
              {t("changePreview.changesHeading", { count: items.length })}
            </h3>
            <ChangeTargetList
              items={items}
              mode="review"
              selectedId={selectedId}
              onSelect={select}
            />
          </section>
        </div>
        <div className="flex min-w-0 flex-col gap-2.5">
          {diffs.map((item) => (
            <FileDiff
              key={item.id}
              item={item}
              ref={(node) => {
                if (node) refs.current.set(item.id, node);
                else refs.current.delete(item.id);
              }}
            />
          ))}
          {diffNote ? <p className="text-xs text-text-muted">{diffNote}</p> : null}
        </div>
      </div>
    </>
  );
}

function Applied({ items }: { items: readonly ChangeItem[] }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Check aria-hidden className="size-4 shrink-0 stroke-[2.5] text-success" />
        <span className="text-sm font-label text-text">
          {t("changePreview.applied.head", { count: items.length })}
        </span>
      </div>
      <ChangeTargetList items={items} mode="progress" defaultStatus="applied" />
    </div>
  );
}

function Failed({ items }: { items: readonly ChangeItem[] }) {
  const { t } = useTranslation();
  const failed = items.filter((item) => item.status === "failed").length;
  const rest = items.length - failed;
  return (
    <div className="flex flex-col gap-2">
      <Alert variant="destructive">
        <AlertCircle aria-hidden />
        <p className="leading-[1.45] text-text">
          <span className="font-label">
            {t("changePreview.failed.head", { failed, count: items.length })}
          </span>
          {rest > 0 ? <> {t("changePreview.failed.rest", { count: rest })}</> : null}
        </p>
      </Alert>
      <ChangeTargetList items={items} mode="progress" defaultStatus="applied" />
    </div>
  );
}

interface Props {
  state: ChangePreviewState;
  items: readonly ChangeItem[];
  summaries: readonly ChangeSummaryLine[];
  /** Shown above "What will happen" while reviewing (a list of what was found, say). */
  lead?: ReactNode;
  /** A line under the diffs while reviewing. */
  diffNote?: string;
}

export function ChangePreviewBody({ state, items, summaries, lead, diffNote }: Props) {
  switch (state) {
    case "computing":
      return <Computing />;
    case "empty":
      return <Empty />;
    case "ready":
      return <Review items={items} summaries={summaries} lead={lead} diffNote={diffNote} />;
    case "applying":
      return <ChangeTargetList items={items} mode="progress" />;
    case "applied":
      return <Applied items={items} />;
    case "failed":
      return <Failed items={items} />;
  }
}
