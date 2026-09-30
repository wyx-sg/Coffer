// frontend/src/pages/sync/SyncRemoteCheck.tsx
//
// "Check repository": ask the daemon what the drafted repository holds before
// anyone saves it — empty (the first push fills it), a Coffer vault (and at
// which layout), some other repository, or unreachable / refused with git's
// own message. Asked of the DRAFT, because the point is to find out before
// the vault starts pushing into it.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useCheckRemote } from "@/lib/hooks/useSync";
import { DEFAULT_BRANCH, type FormState } from "./syncRemoteForm";

const GOOD = new Set(["empty", "vault"]);

export function SyncRemoteCheck({ form, disabled }: { form: FormState; disabled: boolean }) {
  const { t } = useTranslation();
  const check = useCheckRemote();
  const result = check.data;

  return (
    <>
      <Button
        type="button"
        variant="outline"
        disabled={disabled || check.isPending}
        onClick={() =>
          check.mutate({
            url: form.url.trim(),
            branch: form.branch.trim() || DEFAULT_BRANCH,
            credential_ref: form.credentialRef.trim() || null,
          })
        }
      >
        {check.isPending ? t("sync.remote.checking") : t("sync.remote.check")}
      </Button>
      {result ? (
        <span
          className={GOOD.has(result.result) ? "text-xs text-status-ok" : "text-xs text-status-err"}
          role="status"
          data-testid="sync-remote-check"
        >
          {t(`sync.remote.checkResult.${result.result}`, { layout: result.layout ?? "?" })}
          {result.detail ? ` — ${result.detail}` : ""}
        </span>
      ) : check.error ? (
        <span className="text-xs text-status-err" role="status">
          {translateApiError(t, check.error)}
        </span>
      ) : null}
    </>
  );
}
