// src/components/overview/systemTiles.tsx — the Health tiles of Custom tools, CLIs, Secrets and Usage.
//
// The same shape as areaTiles.tsx: each reads its own list hook, so it loads
// and fails on its own. Custom tools and CLIs take their word from the
// attention items of their kinds, like every other area; Secrets and Usage
// have no attention source, so Secrets words what its own list says (a
// secret missing on this Mac, one nothing uses) and Usage shows only its
// period, never a health it does not have.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { useClis } from "@/lib/hooks/useClis";
import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { useUsageSummary } from "@/lib/hooks/useUsage";
import type { SecretRef } from "@/lib/api/secret";
import type { UsageSummary } from "@/lib/api/usage";
import { tileStatus } from "@/lib/overview/health";
import { allUnpriced, formatCost, formatTokens } from "@/lib/usage/format";
import type { AreaProps } from "./areaTiles";
import type { TileContent } from "./HealthTile";
import { QueryTile } from "./QueryTile";

export function CustomToolsTile({ area, items }: AreaProps) {
  const { t, i18n } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useCustomToolGroups()}
      content={(groups) => {
        const calls = groups.reduce((n, g) => n + g.calls_24h, 0);
        const errors = groups.reduce((n, g) => n + g.failures_24h, 0);
        return {
          status: tileStatus(t, area, items, groups.length > 0),
          value: groups.length,
          unit: t("overview.health.customTools.unit", { count: groups.length }),
          summary:
            groups.length > 0
              ? t("overview.health.customTools.calls", {
                  calls: calls.toLocaleString(i18n.language),
                  errors: errors.toLocaleString(i18n.language),
                })
              : t("overview.health.customTools.none"),
        };
      }}
    />
  );
}

/** Up to three names, then "…". */
function firstNames(names: readonly string[]): string {
  return names.length > 3 ? `${names.slice(0, 3).join(", ")}…` : names.join(", ");
}

export function ClisTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useClis()}
      content={(list) => {
        const clis = list.items;
        const skills = new Set(clis.flatMap((c) => c.needed_by.map((n) => n.skill_uid)));
        return {
          status: tileStatus(t, area, items, clis.length > 0),
          value: clis.length,
          unit: t("overview.health.clis.unit", { count: clis.length }),
          summary:
            clis.length === 0
              ? t("overview.health.clis.none")
              : t(
                  skills.size > 0 ? "overview.health.clis.neededBy" : "overview.health.clis.listed",
                  {
                    count: skills.size,
                    names: firstNames(clis.map((c) => c.command)),
                  },
                ),
        };
      }}
    />
  );
}

/** Missing on this Mac is a problem; a secret nothing references is only worth knowing. */
function secretsContent(t: TFunction, refs: readonly SecretRef[]): TileContent {
  const missing = refs.filter((r) => !r.present).length;
  const unused = refs.filter((r) => r.unreferenced).length;
  const users = new Set(
    refs.flatMap((r) => [
      ...r.bindings.map((b) => `${b.destination_kind}:${b.destination_uid}`),
      ...r.cited_by.map((c) => `${c.kind}:${c.uid}`),
      ...r.mentioned_by_skills.map((s) => `skill:${s}`),
    ]),
  );
  return {
    status:
      refs.length === 0
        ? null
        : missing > 0
          ? { tone: "warn", text: t("overview.health.secrets.missing", { count: missing }) }
          : unused > 0
            ? { tone: "ok", text: t("overview.health.secrets.unused", { count: unused }) }
            : { tone: "ok", text: t("overview.health.secrets.ok") },
    value: refs.length,
    unit: t("overview.health.secrets.unit", { count: refs.length }),
    summary:
      refs.length > 0
        ? t("overview.health.secrets.referencedBy", { count: users.size })
        : t("overview.health.secrets.none"),
  };
}

export function SecretsTile({ area }: AreaProps) {
  const { t } = useTranslation();
  return (
    <QueryTile area={area} query={useSecrets()} content={(list) => secretsContent(t, list.refs)} />
  );
}

/** "$4.12 · Anthropic 71% · Acme gateway 29%": the cost, then each provider's share of the tokens. */
function usageSummary(summary: UsageSummary, lang: string): string {
  const tokens = (x: { input_tokens: number; output_tokens: number }) =>
    x.input_tokens + x.output_tokens;
  const total = tokens(summary.totals);
  const byProvider = new Map<string, number>();
  for (const row of summary.rows ?? []) {
    const name = row.connection_name ?? "";
    if (name) byProvider.set(name, (byProvider.get(name) ?? 0) + tokens(row.totals));
  }
  const parts = allUnpriced(summary.totals)
    ? []
    : [formatCost(summary.totals.estimated_cost_usd, lang)];
  if (total > 0) {
    const shares = [...byProvider].sort((a, b) => b[1] - a[1]).slice(0, 2);
    for (const [name, n] of shares) parts.push(`${name} ${Math.round((n / total) * 100)}%`);
  }
  return parts.join(" · ");
}

export function UsageTile({ area }: AreaProps) {
  const { t, i18n } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useUsageSummary({ range: "today", group_by: "model" })}
      content={(summary) => ({
        status: null,
        note: t("overview.health.usage.period"),
        value: formatTokens(
          summary.totals.input_tokens + summary.totals.output_tokens,
          i18n.language,
        ),
        unit: t("overview.health.usage.unit"),
        summary: usageSummary(summary, i18n.language) || null,
      })}
    />
  );
}
