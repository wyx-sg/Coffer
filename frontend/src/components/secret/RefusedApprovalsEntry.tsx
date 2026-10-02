// src/components/secret/RefusedApprovalsEntry.tsx
// What a refusal leaves behind: each refused binding with an "Ask again"
// button. A refused binding stays refused for its target until the destination
// changes or someone asks again; asking widens nothing — the new approval still
// waits for a person (spec secret "Show each change waiting for approval as
// the question it asks"; ask-again route). Renders nothing while nothing is
// refused.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useAskAgain, useRefusedApprovals } from "@/lib/hooks/useApprovals";

export function RefusedApprovalsEntry() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const refused = useRefusedApprovals();
  const askAgain = useAskAgain();
  const rows = refused.data?.approvals ?? [];
  if (rows.length === 0) return null;
  return (
    <section
      aria-label={t("secrets.refused.title", { count: rows.length })}
      className="space-y-2 rounded-lg border border-border-subtle bg-surface-sunken px-3.5 py-2.5"
      data-testid="refused-approvals"
    >
      <p className="text-sm font-semibold text-text">
        {t("secrets.refused.title", { count: rows.length })}
      </p>
      <ul className="space-y-1.5">
        {rows.map((a) => (
          <li key={a.id} className="flex items-center gap-3" data-testid="refused-approval">
            <p className="min-w-0 flex-1 break-words text-xs text-text-muted">{a.description}</p>
            <Button
              size="sm"
              variant="outline"
              disabled={askAgain.isPending}
              onClick={() =>
                askAgain.mutate(a.id, { onSuccess: () => toast.success(t("secrets.refused.asked")) })
              }
            >
              {t("secrets.refused.askAgain")}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
