// src/components/credentials/ScanFindingsStep.tsx — step one of Find plaintext keys: what the scan found, each with a tick.
//
// Each finding says where it is (file and line), the key it is assigned to,
// and the secret it would become. Values are never shown — the scan does not
// return them. Skills that still point at `~/.coffer/secrets/` are listed
// beneath, since moving a file's values does not rewrite those mentions; the
// backend's hand-off asks an agent to rewrite them to use `coffer run` (it
// names files, lines and secret names, never a value).
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { SecretScan } from "@/lib/api/credentials";
import { fileCount, shortPath } from "./scanPlan";

interface Props {
  scan: SecretScan;
  ticked: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onToggleAll: (all: boolean) => void;
  reviewing: boolean;
  onCancel: () => void;
  onReview: () => void;
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
  const { findings, mentions } = scan;
  const count = ticked.size;
  const all = count === findings.length && count > 0;

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("secrets.scan.foundTitle")}</DialogTitle>
        <DialogDescription>
          {t("secrets.scan.foundSummary", {
            count: findings.length,
            files: fileCount(findings),
          })}
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[360px] overflow-y-auto rounded-md border border-border-subtle">
        <table className="w-full text-xs">
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
              <th className="px-2 py-2 font-medium">{t("secrets.scan.foundIn")}</th>
              <th className="px-2 py-2 font-medium">{t("secrets.scan.key")}</th>
              <th className="px-3 py-2 font-medium">{t("secrets.scan.secretName")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {findings.map((f) => {
              const where = shortPath(f.path);
              return (
                <tr key={f.id} className={ticked.has(f.id) ? undefined : "text-text-muted"}>
                  <td className="px-3 py-2 align-top">
                    <Checkbox
                      aria-label={t("secrets.scan.tickOne", { path: where, line: f.line })}
                      checked={ticked.has(f.id)}
                      onChange={() => onToggle(f.id)}
                    />
                  </td>
                  <td className="max-w-[240px] px-2 py-2 align-top">
                    <p className="truncate font-mono text-text" title={f.path}>
                      {where}
                    </p>
                    <p className="text-2xs text-text-muted">
                      {t("secrets.scan.line", { line: f.line })} ·{" "}
                      {t(`secrets.scan.source.${f.source}`)}
                    </p>
                  </td>
                  <td className="px-2 py-2 align-top font-mono">{f.key}</td>
                  <td className="px-3 py-2 align-top font-mono text-text">{f.proposed_name}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {mentions.length > 0 ? (
        <div className="space-y-1 rounded-md bg-surface-sunken px-3 py-2 text-xs text-text-muted">
          <p>{t("secrets.scan.mentions", { count: mentions.length })}</p>
          <ul className="space-y-0.5 font-mono">
            {mentions.map((m) => (
              <li key={`${m.path}:${m.line}`} className="truncate" title={m.path}>
                {m.skill} · {shortPath(m.path)}:{m.line}
              </li>
            ))}
          </ul>
          {scan.handoff ? (
            <div className="pt-1">
              <AgentHandoff prompt={scan.handoff.prompt} size="sm" />
            </div>
          ) : null}
        </div>
      ) : null}
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
