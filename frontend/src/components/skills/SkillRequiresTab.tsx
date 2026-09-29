// frontend/src/components/skills/SkillRequiresTab.tsx
// The Requires tab: the commands this skill's SKILL.md declares it needs
// (spec skill-manager "Show the commands a skill declares it needs"), in the
// order declared, each opening that command's page on the CLIs page — which is
// where a command is looked for on this machine; this tab probes nothing.
// Declaring one changes nothing about delivery, and the tab says so.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Terminal } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import type { SkillOut } from "@/lib/api/skills";

export function SkillRequiresTab({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();

  if (skill.requires.length === 0) {
    return (
      <EmptyState
        icon={Terminal}
        title={t("skills.requires.emptyTitle")}
        description={t("skills.requires.emptyBody")}
      />
    );
  }

  return (
    <section className="flex flex-col gap-3" aria-label={t("skills.detail.tabs.requires")}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t("skills.detail.tabs.requires")}</h3>
        <span className="text-xs text-text-muted">{t("skills.requires.declared")}</span>
        <Button variant="outline" size="sm" className="ml-auto" asChild>
          <Link to="/clis">{t("skills.requires.openClis")}</Link>
        </Button>
      </div>
      <ul className="divide-y divide-border-subtle rounded-xl border border-border-subtle">
        {skill.requires.map((r) => (
          <li key={r.command}>
            <Link
              to={`/clis/${encodeURIComponent(r.command)}`}
              className="flex items-center gap-3 px-4 py-3 transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
            >
              <span className="font-mono text-xs font-label text-text">{r.command}</span>
              <span className="text-xs text-text-muted">
                {r.min_version
                  ? t("skills.requires.minVersion", { version: r.min_version })
                  : t("skills.requires.anyVersion")}
              </span>
              <ChevronRight aria-hidden className="ml-auto size-4 text-text-subtle" />
            </Link>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-muted">{t("skills.requires.stillDelivered")}</p>
    </section>
  );
}
