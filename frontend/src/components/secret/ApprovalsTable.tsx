// src/components/secret/ApprovalsTable.tsx — the changes waiting for approval as one bordered table, and the same table with each one's result.
//
// Columns: [checkbox] · Change (New use / Turn off protection) · Secret · Goes to · Requested by
// · At — or, after approving, Change · Secret · Goes to · Result. The header box selects every
// change. A change sent somewhere says where (kind, name and the slot it fills) and, when the
// daemon names one, the target that receives it.
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Approval, ApprovalBatchResult, SecretRef } from "@/lib/api/secret";
import { formatClock, formatUsDay } from "@/lib/time";
import { approvalSecretName } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

/** "14:03" for today, "Sep 29, 14:03" for another day. */
function when(iso: string, lang: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const clock = formatClock(d);
  return d.toDateString() === now.toDateString()
    ? clock
    : `${formatUsDay(d, lang, d.getFullYear() !== now.getFullYear())}, ${clock}`;
}

function useGoesTo() {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  return (a: Approval): { text: string; detail: string | null } => {
    if (a.op === "disable_protection") return { text: "—", detail: null };
    const where = [a.destination_kind && kindLabel(a.destination_kind), a.destination_label]
      .filter(Boolean)
      .join(" ");
    return {
      text: t("secrets.approvals.sentTo", { where: a.slot ? `${where} (${a.slot})` : where }),
      detail: a.target,
    };
  };
}

const HEAD = "";

interface ListProps {
  approvals: Approval[];
  rows: SecretRef[];
  selected: ReadonlySet<string>;
  onToggle: (id: string, on: boolean) => void;
  onToggleAll: (on: boolean) => void;
}

export function ApprovalsList({ approvals, rows, selected, onToggle, onToggleAll }: ListProps) {
  const { t, i18n } = useTranslation();
  const goesTo = useGoesTo();
  const ticked = approvals.filter((a) => selected.has(a.id)).length;
  return (
    <div className="max-h-[56vh] overflow-hidden rounded-xl border border-border bg-surface-raised">
      <Table containerClassName="max-h-[56vh]" className="table-fixed">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={`${HEAD} w-[44px]`}>
              <Checkbox
                aria-label={t("secrets.approvals.selectAll")}
                checked={approvals.length > 0 && ticked === approvals.length}
                indeterminate={ticked > 0 && ticked < approvals.length}
                onChange={(e) => onToggleAll(e.target.checked)}
              />
            </TableHead>
            <TableHead className={`${HEAD} w-[120px]`}>{t("secrets.approvals.change")}</TableHead>
            <TableHead className={`${HEAD} w-[190px]`}>{t("secrets.approvals.secret")}</TableHead>
            <TableHead className={HEAD}>{t("secrets.approvals.goesTo")}</TableHead>
            <TableHead className={`${HEAD} w-[190px]`}>
              {t("secrets.approvals.requestedBy")}
            </TableHead>
            <TableHead className={`${HEAD} w-[110px]`}>{t("secrets.approvals.at")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {approvals.map((a) => {
            const name = approvalSecretName(a, rows);
            const where = goesTo(a);
            return (
              <TableRow key={a.id} data-testid="approval-row">
                <TableCell>
                  <Checkbox
                    checked={selected.has(a.id)}
                    onChange={(e) => onToggle(a.id, e.target.checked)}
                    aria-label={t("secrets.approvals.select", {
                      name: name || t(`secrets.approvals.op.${a.op}`),
                    })}
                  />
                </TableCell>
                <TableCell className="text-xs text-text">
                  {t(`secrets.approvals.op.${a.op}`)}
                </TableCell>
                <TableCell className="truncate font-mono text-xs text-text">
                  {name || "—"}
                </TableCell>
                <TableCell className="text-xs text-text-muted">
                  <p>{where.text}</p>
                  {where.detail ? (
                    <p className="break-all text-text-subtle">{where.detail}</p>
                  ) : null}
                </TableCell>
                <TableCell className="text-xs text-text-muted">
                  {t(`secrets.approvals.via.${a.requested_by}`, { defaultValue: a.requested_by })}
                </TableCell>
                <TableCell className="text-xs tabular-nums text-text-muted">
                  {when(a.created_at, i18n.language)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

interface ResultProps {
  /** The changes the confirmation covered, as they were listed. */
  approvals: Approval[];
  rows: SecretRef[];
  results: ApprovalBatchResult[];
}

export function ApprovalsResult({ approvals, rows, results }: ResultProps) {
  const { t } = useTranslation();
  const goesTo = useGoesTo();
  return (
    <div className="max-h-[56vh] overflow-hidden rounded-xl border border-border bg-surface-raised">
      <Table containerClassName="max-h-[56vh]" className="table-fixed">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={`${HEAD} w-[120px]`}>{t("secrets.approvals.change")}</TableHead>
            <TableHead className={`${HEAD} w-[190px]`}>{t("secrets.approvals.secret")}</TableHead>
            <TableHead className={HEAD}>{t("secrets.approvals.goesTo")}</TableHead>
            <TableHead className={`${HEAD} w-[300px]`}>{t("secrets.approvals.result")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {approvals.map((a) => {
            const done = results.find((r) => r.id === a.id);
            const approved = done?.outcome === "approved";
            return (
              <TableRow key={a.id} data-testid="batch-review-row">
                <TableCell className="text-xs text-text">
                  {t(`secrets.approvals.op.${a.op}`)}
                </TableCell>
                <TableCell className="truncate font-mono text-xs text-text">
                  {approvalSecretName(a, rows) || "—"}
                </TableCell>
                <TableCell className="text-xs text-text-muted">{goesTo(a).text}</TableCell>
                <TableCell className="text-xs">
                  {approved ? (
                    <span className="inline-flex items-center gap-1.5 text-success">
                      <Check className="size-3.5" aria-hidden />
                      {t("secrets.approvals.batch.approved")}
                    </span>
                  ) : (
                    <p className="text-warning">
                      <span className="font-label">{t("secrets.approvals.batch.skippedWord")}</span>{" "}
                      <span className="text-text-muted">
                        {t(`secrets.approvals.batch.skipped.${done?.reason ?? "not_pending"}`)}
                      </span>
                    </p>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
