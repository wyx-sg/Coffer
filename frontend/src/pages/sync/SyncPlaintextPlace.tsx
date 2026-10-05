// frontend/src/pages/sync/SyncPlaintextPlace.tsx
//
// One place a round found a plaintext secret (spec vault-sync "Show a plaintext
// finding in its file"): a row that opens in place to the lines around it,
// fetched when first opened, with every value masked by the daemon — the value
// never reaches the page. Beside the lines: whether the file is new or changed,
// whether the line is already on the remote, each masked value's shape in
// words, and for a changed file its masked diff behind "Show changes".
import { ChevronRight } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { PlaintextContext, SyncProblem } from "@/lib/api/sync";
import { usePlaintextContext } from "@/lib/hooks/useSync";
import { cn } from "@/lib/utils";
import { parseUnifiedDiff } from "./syncConflictFormat";
import { DiffTable } from "./SyncDiffTable";

type Finding = NonNullable<SyncProblem["plaintext"]>[number];
type Line = PlaintextContext["lines"][number];
type Value = Line["values"][number];

const NOTE = "text-xs text-text-muted";

/** The masked text with each masked value highlighted. */
function LineText({ line }: { line: Line }) {
  const parts: ReactNode[] = [];
  let at = 0;
  for (const v of line.values) {
    if (v.start > at) parts.push(line.text.slice(at, v.start));
    parts.push(
      <mark key={v.start} className="rounded-sm bg-danger-soft px-px text-danger">
        {line.text.slice(v.start, v.end)}
      </mark>,
    );
    at = v.end;
  }
  parts.push(line.text.slice(at));
  return <>{parts}</>;
}

function RuleTag({ rule }: { rule: string }) {
  const { t } = useTranslation();
  return (
    <code
      className="ml-1.5 font-mono text-2xs text-text-subtle"
      title={t("sync.problem.plaintext_found.foundByRule", { rule })}
      data-testid="sync-plaintext-rule"
    >
      {rule}
    </code>
  );
}

function ShapeText({ value }: { value: Value }) {
  const { t } = useTranslation();
  const s = value.shape;
  const classes = s.classes.map((c) => t(`sync.problem.plaintext_found.classes.${c}`)).join(", ");
  const bits = [t("sync.problem.plaintext_found.shape", { length: s.length, classes })];
  if (s.prefix) bits.push(t("sync.problem.plaintext_found.prefix", { prefix: s.prefix }));
  if (s.hint) bits.push(t(`sync.problem.plaintext_found.hints.${s.hint}`, { word: s.word }));
  return (
    <li>
      <code className="font-mono">{value.key}</code> — {bits.join(" · ")}
      {value.rule ? <RuleTag rule={value.rule} /> : null}
    </li>
  );
}

function Changes({ data }: { data: PlaintextContext }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (data.change !== "modified") return null;
  if (data.diff == null)
    return <p className={NOTE}>{t("sync.problem.plaintext_found.tooLarge")}</p>;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
          {open
            ? t("sync.problem.plaintext_found.hideChanges")
            : t("sync.problem.plaintext_found.showChanges")}
        </Button>
        <LineCounts added={data.added} removed={data.removed} />
      </div>
      {open ? (
        <DiffTable lines={parseUnifiedDiff(data.diff).lines} testId="sync-plaintext-diff" />
      ) : null}
    </div>
  );
}

function Body({ data }: { data: PlaintextContext }) {
  const { t } = useTranslation();
  const flagged = data.lines.find((l) => l.number === data.line);
  return (
    <div className="flex flex-col gap-2" data-testid="sync-plaintext-context">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {data.change === "added"
            ? t("sync.problem.plaintext_found.newFile")
            : t("sync.problem.plaintext_found.changedFile")}
        </Badge>
        {data.on_remote ? (
          <span className={NOTE}>{t("sync.problem.plaintext_found.onRemote")}</span>
        ) : null}
      </div>
      <div className="overflow-x-auto rounded-md border border-border-subtle bg-surface font-mono text-xs leading-5">
        {data.lines.map((line) => (
          <div
            key={line.number}
            data-flagged={line.number === data.line || undefined}
            className={cn(
              "grid grid-cols-[40px_minmax(0,1fr)]",
              line.number === data.line && "bg-danger-soft/60",
            )}
          >
            <span className="select-none pr-2 text-right text-text-subtle">{line.number}</span>
            <span className="whitespace-pre pr-2.5 text-text">
              <LineText line={line} />
            </span>
          </div>
        ))}
      </div>
      {flagged && flagged.values.length > 0 ? (
        <ul className="flex flex-col gap-0.5 text-xs text-text-muted">
          {flagged.values.map((v) => (
            <ShapeText key={v.start} value={v} />
          ))}
        </ul>
      ) : null}
      <p className="text-2xs text-text-subtle">{t("sync.problem.plaintext_found.masked")}</p>
      <Changes data={data} />
    </div>
  );
}

export function PlaintextPlace({ finding }: { finding: Finding }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const query = usePlaintextContext(finding.path, finding.line, open);
  return (
    <li className="flex flex-col gap-1.5">
      <button
        type="button"
        aria-expanded={open}
        aria-label={t("sync.problem.plaintext_found.showPlace", {
          path: finding.path,
          line: finding.line,
        })}
        onClick={() => setOpen((v) => !v)}
        className="flex flex-wrap items-center gap-x-2 text-left"
      >
        <ChevronRight
          aria-hidden
          className={cn(
            "size-3 shrink-0 text-text-subtle transition-transform",
            open && "rotate-90",
          )}
        />
        <code className="font-mono text-xs text-text-muted">
          {t("sync.problem.plaintext_found.where", { path: finding.path, line: finding.line })}
        </code>
        <span className="text-text-muted">
          {finding.key === "token"
            ? t("sync.problem.plaintext_found.token")
            : t("sync.problem.plaintext_found.key", { key: finding.key })}
        </span>
        {finding.rule ? <RuleTag rule={finding.rule} /> : null}
      </button>
      {open ? (
        <div className="pb-1 pl-5">
          {query.isLoading ? <Skeleton className="h-16 w-full" /> : null}
          {query.error ? (
            <p className="text-xs text-danger" role="alert">
              {translateApiError(t, query.error)}
            </p>
          ) : null}
          {query.data ? <Body data={query.data} /> : null}
        </div>
      ) : null}
    </li>
  );
}
