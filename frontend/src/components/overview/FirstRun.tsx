// src/components/overview/FirstRun.tsx — what the Overview says before any agent is registered: connect one, then add what they share.
//
// First the agents card (FirstRunAgents): the supported agents, which were
// found on this Mac, and connecting them through the review that shows every
// file change first — or, with none found, scanning again. Below, the areas
// an agent shares, each with its first step; "each can wait until you need
// it". An area whose sidebar entry carries an experimental feature is offered
// only while that feature is on (Overview boards 1.3.03, 1.3.07).
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { isFeatureOn, useFeatureMap } from "@/lib/hooks/useFeatures";
import { NAV_ENTRIES } from "@/lib/navigation";
import { Section } from "@/components/Section";
import { FirstRunAgents } from "./FirstRunAgents";

/** The areas agents share, in sidebar order, each with its first-step copy key. */
const SHARED: readonly { to: string; id: string }[] = [
  { to: "/mcp-servers", id: "mcpServers" },
  { to: "/skills", id: "skills" },
  { to: "/knowledge", id: "knowledge" },
  { to: "/model-providers", id: "providers" },
  { to: "/channels", id: "channels" },
];

export function FirstRun() {
  const { t } = useTranslation();
  const features = useFeatureMap();
  const shared = SHARED.filter((s) =>
    isFeatureOn(features, NAV_ENTRIES.find((e) => e.to === s.to)?.feature),
  );

  return (
    <>
      <FirstRunAgents />
      <Section
        as="h2"
        gap="snug"
        labelled
        title={t("overview.firstRun.thenTitle")}
        help={t("overview.firstRun.thenHint")}
      >
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {shared.map((s) => {
            const entry = NAV_ENTRIES.find((e) => e.to === s.to);
            if (!entry) return null;
            const Icon = entry.icon;
            return (
              <li
                key={s.id}
                className="flex h-24 flex-col gap-2 rounded-xl border border-border bg-surface-raised px-4 py-3.5"
              >
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <Icon className="size-[15px] text-text-subtle" strokeWidth={1.75} aria-hidden />
                  {t(entry.labelKey)}
                </span>
                <span className="truncate text-sm text-text-muted">
                  {t(`overview.firstRun.shared.${s.id}.body`)}
                </span>
                <Link
                  to={s.to}
                  className="mt-auto inline-flex items-center gap-1 self-start rounded-xs text-xs font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  {t(`overview.firstRun.shared.${s.id}.cta`)}
                  <ArrowRight className="size-3" aria-hidden />
                </Link>
              </li>
            );
          })}
        </ul>
      </Section>
    </>
  );
}
