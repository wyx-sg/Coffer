// components/chat/ApprovalCard.tsx
// Generic human-approval card. When a turn pauses on an approval request, this
// card names the tool and its inputs and lets the user allow or deny. It is a
// platform capability — Coffer's built-in agent does not trigger it, but any
// agent that requests per-call approval renders through this same card.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PendingApproval } from "@/lib/hooks/useChatTurn";

interface Props {
  approval: PendingApproval;
  /** Called with the decision; may be async — the buttons disable until it settles. */
  onDecide: (behavior: "allow" | "deny") => void | Promise<void>;
  disabled?: boolean;
}

export function ApprovalCard({ approval, onDecide, disabled = false }: Props) {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const busy = submitting || disabled;

  const decide = async (behavior: "allow" | "deny") => {
    if (busy) return;
    setSubmitting(true);
    try {
      await onDecide(behavior);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-t border-status-warn/40 bg-status-warn/10 px-4 py-3">
      <div className="flex items-start gap-2">
        <ShieldAlert
          className="mt-0.5 size-4 shrink-0 text-status-warn"
          aria-hidden
        />
        <div className="flex-1 space-y-2 text-sm">
          <p className="font-medium text-foreground">{t("chat.approval.title")}</p>
          <p className="text-xs text-muted-foreground">
            {t("chat.approval.tool")}:{" "}
            <span className="font-mono text-foreground">{approval.tool_name}</span>
          </p>
          <pre className="max-h-40 overflow-auto rounded bg-background p-2 text-xs leading-relaxed">
            {JSON.stringify(approval.tool_input, null, 2)}
          </pre>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => void decide("allow")}>
              {t("chat.approval.allow")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void decide("deny")}
            >
              {t("chat.approval.deny")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
