// src/components/agents/tabs/FromCofferRow.tsx — "From Coffer": what Coffer manages for this agent, as one row.
//
// Boards 2.1.20 and 2.1.25. The Skills and MCP servers tabs open with Coffer's
// part: a section (title, one line) and a single hairline row — the count, the
// first five names in mono with "+N more", and a link to that kind's page
// filtered to this agent. Coffer-managed items are never listed one by one
// here; the agent's own items follow in their own section.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, type LucideIcon } from "lucide-react";

import { Section } from "@/components/Section";

/** How many names the row spells out before "+N more". */
const NAMES_SHOWN = 5;

interface Props {
  icon: LucideIcon;
  /** The section's one-line explanation. */
  description: ReactNode;
  /** The row's headline, e.g. "12 skills from Coffer". */
  title: string;
  /** Every name; the row shows the first five. */
  names: readonly string[];
  /** The link's label, e.g. "Open Skills". */
  linkLabel: string;
  /** Where the link goes, e.g. `/skills?agent=<uid>`. */
  to: string;
  testId?: string;
}

export function FromCofferRow({
  icon: Icon,
  description,
  title,
  names,
  linkLabel,
  to,
  testId,
}: Props) {
  const { t } = useTranslation();
  const shown = names.slice(0, NAMES_SHOWN);
  const more = names.length - shown.length;
  return (
    <Section as="h2" title={t("agents.fromCoffer.title")} gap="tight" testId={testId}>
      <p className="mb-1 text-xs text-text-muted">{description}</p>
      <div className="flex items-center gap-3 border-y border-border-subtle px-1 py-3">
        <Icon className="size-4 shrink-0 text-text-subtle" aria-hidden />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-sm font-medium text-text">{title}</span>
          {shown.length > 0 ? (
            <span className="truncate font-mono text-xs text-text-muted">
              {shown.join(" · ")}
              {more > 0 ? ` · ${t("agents.fromCoffer.more", { count: more })}` : ""}
            </span>
          ) : null}
        </div>
        <Link
          to={to}
          className="inline-flex shrink-0 items-center gap-0.5 text-xs font-medium text-accent-text hover:underline"
        >
          {linkLabel}
          <ChevronRight className="size-3.5" aria-hidden />
        </Link>
      </div>
    </Section>
  );
}
