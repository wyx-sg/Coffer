// frontend/src/components/knowledge/KnowledgeImportParts.tsx
//
// The parts of a source's line an import adds (spec knowledge "Import a
// Confluence page as a readable source with its attachments"): where it came
// from — its system, a link to it, its version and when it was fetched, never
// that it was verified — and, when the import left something behind, a
// Partial mark naming what.
import { useTranslation } from "react-i18next";

import { WebLink } from "@/components/knowledge/KnowledgeLink";
import { StatusPill } from "@/components/status/StatusPill";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { FileOut } from "@/lib/api/knowledge";

export function SourceOrigin({ origin }: { origin: Record<string, string> }) {
  const { t, i18n } = useTranslation();
  const fetched = Date.parse(origin.fetched_at ?? "");
  const name = origin.title || (origin.page_id ? `#${origin.page_id}` : origin.url);
  return (
    <span data-testid="source-origin" className="inline-flex flex-wrap items-center gap-x-1">
      {t("knowledge.document.origin", {
        system: origin.system || t("knowledge.document.originWeb"),
      })}
      <WebLink href={origin.url}>{name}</WebLink>
      {origin.version ? (
        <span>{t("knowledge.document.originVersion", { version: origin.version })}</span>
      ) : null}
      {Number.isNaN(fetched) ? null : (
        <span>
          {t("knowledge.document.fetched", {
            date: new Date(fetched).toLocaleDateString(i18n.language, {
              month: "short",
              day: "numeric",
              year: "numeric",
            }),
          })}
        </span>
      )}
    </span>
  );
}

export function PartialImport({ report }: { report: NonNullable<FileOut["import_report"]> }) {
  const { t } = useTranslation();
  const left = [
    ...((report.missing as string[] | undefined) ?? []),
    ...((report.unsupported as string[] | undefined) ?? []),
  ];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} data-testid="import-partial">
          <StatusPill tone="warn">{t("knowledge.document.partial")}</StatusPill>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        <p>{t("knowledge.document.partialHint")}</p>
        <ul className="mt-1 list-disc pl-4">
          {left.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}
