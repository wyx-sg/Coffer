// src/components/secret/ScanFindingsStep.tsx — step one of Find plaintext keys: what the scan found, each with a tick.
//
// Findings are grouped by source, Skills then MCP servers. Each row names the
// resource, where the value sits (a skill's `path:line`, a server's `env KEY`
// or `header KEY`) and what it becomes. Values are never shown — the scan
// does not return them.
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { SecretScan, SecretScanFinding } from "@/lib/api/secret";
import { placeOf, resourceCount } from "./scanPlan";

interface Props {
  scan: SecretScan;
  ticked: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onToggleAll: (all: boolean) => void;
  reviewing: boolean;
  onCancel: () => void;
  onReview: () => void;
}

const SOURCES = ["skill", "mcp_server"] as const;

function becomes(f: SecretScanFinding, t: (key: string) => string): string {
  return f.source === "skill" && f.proposed_name
    ? `coffer://secret/${f.proposed_name}`
    : t("secrets.scan.ownSecret");
}

export function ScanFindingsStep({
  scan,
  ticked,
  onToggle,
  onToggleAll,
  reviewing,
  onCancel,
  onReview,
}: Props) {
  const { t } = useTranslation();
  const { findings } = scan;
  const count = ticked.size;
  const all = count === findings.length && count > 0;

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("secrets.scan.foundTitle")}</DialogTitle>
        <DialogDescription>
          {t("secrets.scan.foundSummary", {
            count: findings.length,
            resources: resourceCount(findings),
          })}
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[380px] min-w-0 overflow-auto rounded-md border border-border-subtle">
        <table className="w-full table-fixed text-xs">
          <thead className="sticky top-0 bg-surface-raised text-left text-text-muted">
            <tr className="border-b border-border-subtle">
              <th className="w-8 px-3 py-2">
                <Checkbox
                  aria-label={t("secrets.scan.tickAll")}
                  checked={all}
                  indeterminate={count > 0 && !all}
                  onChange={(e) => onToggleAll(e.target.checked)}
                />
              </th>
              <th className="w-[26%] px-2 py-2 font-medium">{t("secrets.scan.resource")}</th>
              <th className="w-[38%] px-2 py-2 font-medium">{t("secrets.scan.foundIn")}</th>
              <th className="px-3 py-2 font-medium">{t("secrets.scan.becomes")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {SOURCES.map((source) => {
              const group = findings.filter((f) => f.source === source);
              if (group.length === 0) return null;
              return (
                <Fragment key={source}>
                  <tr className="bg-surface-sunken">
                    <th
                      colSpan={4}
                      scope="colgroup"
                      className="px-3 py-1.5 text-left text-2xs font-medium uppercase tracking-wide text-text-muted"
                    >
                      {t(`secrets.scan.source.${source}`)}
                    </th>
                  </tr>
                  {group.map((f) => {
                    const place = placeOf(f);
                    return (
                      <tr key={f.id} className={ticked.has(f.id) ? undefined : "text-text-muted"}>
                        <td className="px-3 py-2 align-top">
                          <Checkbox
                            aria-label={t("secrets.scan.tickOne", {
                              resource: f.resource,
                              place,
                            })}
                            checked={ticked.has(f.id)}
                            onChange={() => onToggle(f.id)}
                          />
                        </td>
                        <td className="truncate px-2 py-2 align-top text-text" title={f.resource}>
                          {f.resource}
                        </td>
                        <td className="px-2 py-2 align-top font-mono">
                          <div className="truncate" title={place}>
                            {place}
                          </div>
                          {f.rule ? (
                            <div
                              className="truncate text-2xs text-text-subtle"
                              title={t("secrets.scan.foundByRule", { rule: f.rule })}
                              data-testid="scan-finding-rule"
                            >
                              {f.rule}
                            </div>
                          ) : null}
                        </td>
                        <td
                          className="truncate px-3 py-2 align-top font-mono text-text"
                          title={becomes(f, t)}
                        >
                          {becomes(f, t)}
                        </td>
                      </tr>
                    );
                  })}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-muted">{t("secrets.scan.hint")}</p>
      <DialogFooter className="items-center">
        <span className="mr-auto text-xs text-text-muted">
          {t("secrets.scan.ticked", { count, total: findings.length })}
        </span>
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={count === 0 || reviewing} onClick={onReview}>
          {reviewing ? t("secrets.scan.reviewing") : t("secrets.scan.review", { count })}
        </Button>
      </DialogFooter>
    </>
  );
}
