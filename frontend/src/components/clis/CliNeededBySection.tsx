// src/components/clis/CliNeededBySection.tsx — "Needed by": Coffer itself, the skills and MCP servers that call the command, one row each (Name · Kind · Needs · →).
//
// A row opens that skill's Requires tab or that server's page; Coffer's own row
// (git, for the vault's history and sync) opens nothing. A tool added by
// hand that nothing needs says so instead of showing an empty table.
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { Cli } from "@/lib/api/clis";
import { withProfiles } from "@/lib/clis/format";
import { CliSection } from "./CliField";

const GRID = "grid grid-cols-[minmax(0,1fr)_110px_150px_16px] items-center gap-2";

interface Row {
  key: string;
  name: string;
  /** Where the row opens; Coffer itself has no page to open. */
  to: string | null;
  kind: string;
  needs: string;
}

export function CliNeededBySection({ cli }: { cli: Cli }) {
  const { t } = useTranslation();
  const outdated = cli.status === "outdated";
  const rows: Row[] = [
    ...(cli.needed_by_coffer.length > 0
      ? [
          {
            key: "coffer",
            name: "Coffer",
            to: null,
            kind: t("clis.detail.kind.coffer"),
            needs: cli.needed_by_coffer.map((u) => t(`clis.cofferUseShort.${u}`)).join(" · "),
          },
        ]
      : []),
    ...cli.needed_by_servers.map((s) => ({
      key: `server-${s.server_uid}`,
      name: s.server_name,
      to: `/mcp-servers/${encodeURIComponent(s.server_name)}`,
      kind: t("clis.detail.kind.server"),
      needs: t("clis.detail.startsWith", { launcher: s.launcher }),
    })),
    ...cli.needed_by.map((n) => ({
      key: `skill-${n.skill_uid}`,
      name: withProfiles(n.skill_name, n.profiles),
      to: `/skills/${encodeURIComponent(n.skill_name)}/requires`,
      kind: t("clis.detail.kind.skill"),
      needs: n.min_version ? `≥ ${n.min_version}` : "—",
    })),
  ];
  return (
    <CliSection title={t("clis.detail.sections.neededBy")} note={t("clis.detail.neededByNote")}>
      {rows.length === 0 ? (
        <p className="border-t border-border-subtle pt-2 text-sm text-text-muted">
          {t("clis.detail.neededByNothing")}
        </p>
      ) : (
        <>
          <div
            className={`${GRID} h-[26px] border-t border-border-subtle text-2xs font-semibold text-text-subtle`}
          >
            <span>{t("clis.detail.cols.name")}</span>
            <span>{t("clis.detail.cols.kind")}</span>
            <span>{t("clis.detail.cols.needs")}</span>
            <span />
          </div>
          {rows.map((r) => {
            const cells = (
              <>
                <span className="truncate font-mono text-xs font-label">{r.name}</span>
                <span className="text-xs text-text-muted">{r.kind}</span>
                <span
                  className={`truncate text-xs ${outdated && r.needs.startsWith("≥") ? "text-warning" : "text-text-muted"}`}
                >
                  {r.needs}
                </span>
              </>
            );
            return r.to === null ? (
              <div key={r.key} className={`${GRID} h-9 border-t border-border-subtle text-text`}>
                {cells}
                <span />
              </div>
            ) : (
              <Link
                key={r.key}
                to={r.to}
                className={`${GRID} h-9 border-t border-border-subtle text-text hover:bg-surface-hover`}
              >
                {cells}
                <ArrowRight className="size-[13px] text-text-subtle" aria-hidden />
              </Link>
            );
          })}
        </>
      )}
    </CliSection>
  );
}
