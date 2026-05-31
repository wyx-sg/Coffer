// frontend/src/components/chat/ConfirmationCard.tsx
//
// A tool the runtime is blocked on, awaiting approve/deny. Wired to the
// /confirm endpoint by the parent via onApprove / onDeny.
import { useTranslation } from "react-i18next";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PendingConfirmation } from "./useChatStream";
import { summarizeArgs } from "./useChatStream";

export function ConfirmationCard({
  confirmation,
  onApprove,
  onDeny,
}: {
  confirmation: PendingConfirmation;
  onApprove: () => void;
  onDeny: () => void;
}) {
  const { t } = useTranslation();
  const args = summarizeArgs(confirmation.args);
  return (
    <div
      className="rounded-md border border-amber-500/50 bg-amber-500/5 px-4 py-3"
      role="alertdialog"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <ShieldAlert className="size-4 shrink-0 text-amber-600" />
        {t("chat.confirm.title", { tool: confirmation.tool })}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{t("chat.confirm.body")}</p>
      {args && args !== "{}" ? (
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded bg-muted/60 p-2 font-mono text-[11px] text-muted-foreground">
          {args}
        </pre>
      ) : null}
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDeny}>
          {t("chat.confirm.deny")}
        </Button>
        <Button size="sm" onClick={onApprove}>
          {t("chat.confirm.approve")}
        </Button>
      </div>
    </div>
  );
}
