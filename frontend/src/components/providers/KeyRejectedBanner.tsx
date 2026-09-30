// src/components/providers/KeyRejectedBanner.tsx — the endpoint refuses the stored key: who fails because of it, and Replace key.
import { useTranslation } from "react-i18next";
import { CircleAlert, KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { useUserNames } from "./useUserNames";

interface Props {
  /** "401" / "403" when the answer named one. */
  status: string | null;
  use: ProviderUse;
  /** Absent for a keyless provider — there is nothing to replace. */
  onReplace?: () => void;
}

export function KeyRejectedBanner({ status, use, onReplace }: Props) {
  const { t } = useTranslation();
  const users = useUserNames(use);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl bg-danger-soft px-4 py-3">
      <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-label text-text">
          {status
            ? t("providers.rejected.title", { status })
            : t("providers.rejected.titleNoStatus")}
        </span>
        <span className="text-xs text-text-muted">
          {users ? t("providers.rejected.bodyUsed", { users }) : t("providers.rejected.bodyUnused")}
        </span>
      </div>
      {onReplace ? (
        <Button variant="outline" size="sm" onClick={onReplace}>
          <KeyRound aria-hidden /> {t("providers.key.replace")}
        </Button>
      ) : null}
    </div>
  );
}
