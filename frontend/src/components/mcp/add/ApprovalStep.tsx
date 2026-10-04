// frontend/src/components/mcp/add/ApprovalStep.tsx — shown after an add whose
// secret goes to a new place (a pending `bind` approval, spec secret "Hold a
// secret for a new destination until a person approves it"; board 4.1.29):
// the servers are registered, the secret is released once someone approves it in
// the Coffer app. Neither a success nor a failure, so it is said before the
// dialog lets go: a warning block naming the secret, the consequence and Open
// approvals, then the servers added and the secrets still waiting; Done only.
import { useTranslation } from "react-i18next";
import { Check, Clock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";

export interface AddedServer {
  name: string;
  /** "stdio · npx" / "Streamable HTTP". */
  summary: string;
  /** Who can call it, as a phrase ("all agents"). */
  reach: string;
  /** The variables / headers whose secret waits; empty when none does. */
  waiting: string[];
}

interface Props {
  added: AddedServer[];
  onDone: () => void;
}

export function ApprovalStep({ added, onDone }: Props) {
  const { t } = useTranslation();
  const waitingServers = added.filter((s) => s.waiting.length > 0);
  const keys = [...new Set(waitingServers.flatMap((s) => s.waiting))];
  const names = waitingServers.map((s) => s.name).join(", ");
  return (
    <>
      <div role="status" className="flex items-start gap-2.5 rounded-lg bg-warning-soft p-3">
        <Clock aria-hidden className="mt-px size-4 shrink-0 text-warning" />
        <div className="flex min-w-0 grow flex-col gap-1">
          <p className="text-sm font-label text-text">
            {t("mcp.add.approval.head", { count: keys.length, keys: keys.join(", ") })}
          </p>
          <p className="text-xs leading-snug text-text-muted">
            {t("mcp.add.approval.body", { count: waitingServers.length, names })}
          </p>
          <div className="pt-1">
            <Button variant="outline" size="sm" onClick={() => openApprovalsSheet()}>
              {t("mcp.add.openApprovals")}
            </Button>
          </div>
        </div>
      </div>
      <ul className="border-t border-border-subtle">
        {added.map((s) => (
          <li key={s.name}>
            <div className="flex min-h-10 items-center gap-2.5 border-b border-border-subtle">
              <Check aria-hidden className="size-4 shrink-0 text-success" />
              <span className="font-mono text-sm font-medium text-text">{s.name}</span>
              <span className="text-xs text-text-muted">{s.summary}</span>
              <span className="ml-auto text-xs text-text-muted">
                {t("mcp.add.approval.added", { reach: s.reach })}
              </span>
            </div>
            {s.waiting.map((key) => (
              <div
                key={key}
                className="flex min-h-10 items-center gap-2.5 border-b border-border-subtle"
              >
                <Clock aria-hidden className="size-4 shrink-0 text-warning" />
                <span className="font-mono text-sm text-text">{key}</span>
                <span className="text-xs text-text-muted">{t("mcp.add.approval.secret")}</span>
                <span className="ml-auto text-xs text-warning">
                  {t("mcp.add.approval.waiting")}
                </span>
              </div>
            ))}
          </li>
        ))}
      </ul>
      <DialogFooter>
        <Button onClick={onDone}>{t("common.done")}</Button>
      </DialogFooter>
    </>
  );
}
