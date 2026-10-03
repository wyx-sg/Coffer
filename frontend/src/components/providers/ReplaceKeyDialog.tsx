// src/components/providers/ReplaceKeyDialog.tsx — replace the value behind a provider's secret, tested first.
//
// The pasted key is checked as it arrives (no Test button): the endpoint's
// models are listed with the NEW key inline, before anything is written. Replace PATCHes `secret_value`: the daemon overwrites the value
// behind the same ref (the agents' config files only name the ref, so they do
// not change). A key already in use does not change at once — the new value
// waits behind a pending `replace_value` approval in the Coffer app (spec
// secret "Hold a replaced value in use until a person approves it") — so
// after the write the pending list is read again, and while an approval for
// this ref waits the dialog says so and offers Review instead of closing.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { openApprovalsSheet, usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useReplaceProviderKey } from "@/lib/hooks/useProviders";
import { pendingReplaceFor } from "@/lib/providers/approvals";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ProbeResult } from "./ProbeResult";
import { useEndpointTest } from "./useEndpointTest";
import { useUserNames } from "./useUserNames";

interface Props {
  open: boolean;
  provider: Provider;
  use: ProviderUse;
  onClose: () => void;
}

export function ReplaceKeyDialog({ open, provider, use, onClose }: Props) {
  const { t } = useTranslation();
  const replace = useReplaceProviderKey();
  const test = useEndpointTest(t);
  const approvals = usePendingApprovals();
  const users = useUserNames(use);
  const [secret, setSecret] = useState("");
  const [written, setWritten] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSecret("");
    setWritten(false);
    test.reset();
    replace.reset();
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Check the key once the paste settles: nothing is written by a check.
  const runTest = useRef(test.run);
  runTest.current = test.run;
  useEffect(() => {
    if (!open || !secret) return;
    const timer = setTimeout(() => {
      void runTest.current({
        provider: provider.protocol,
        base_url: provider.base_url,
        secret_value: secret,
      });
    }, 500);
    return () => clearTimeout(timer);
  }, [open, secret, provider.protocol, provider.base_url]);

  const pending = pendingReplaceFor(approvals.data?.approvals, provider.secret_ref);
  const waiting = written && pending !== null;

  const submit = async () => {
    try {
      await replace.mutateAsync({ uid: provider.uid, secret });
    } catch {
      return; // rendered inline below
    }
    const fresh = await approvals.refetch();
    if (pendingReplaceFor(fresh.data?.approvals, provider.secret_ref)) setWritten(true);
    else onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent aria-describedby={undefined} className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("providers.replace.title")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-label text-text">{t("providers.replace.secret")}</span>
            <span className="inline-flex items-center gap-1.5">
              <KeyRound className="size-3.5 text-text-muted" aria-hidden />
              <span className="text-xs text-text-muted">{t("providers.key.secretPrefix")}</span>
              <span className="font-mono text-xs">{provider.secret_ref}</span>
            </span>
          </div>
          {waiting ? (
            <div
              role="status"
              className="flex flex-col gap-2 rounded-lg bg-warning-soft px-3 py-2.5"
            >
              <StatusWord tone="warn">{t("providers.key.pending")}</StatusWord>
              <span className="text-xs text-text-muted">{t("providers.replace.pendingBody")}</span>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pr-secret" required>
                  {t("providers.replace.newKey")}
                </Label>
                <PasswordInput
                  id="pr-secret"
                  autoComplete="off"
                  className="font-mono text-xs"
                  value={secret}
                  onChange={(e) => {
                    setSecret(e.target.value);
                    test.reset();
                  }}
                />
                <p className="text-xs text-text-muted">
                  {t("providers.replace.hint")}{" "}
                  <Link
                    to="/secrets"
                    className="font-label text-accent-text no-underline hover:underline"
                  >
                    {t("providers.key.manage")}
                  </Link>
                </p>
              </div>
              <ProbeResult
                result={test.result}
                pending={test.isPending}
                okNote={(count) =>
                  users
                    ? t("providers.test.replaceOkUsed", { count, users })
                    : t("providers.test.replaceOk", { count })
                }
                failNote={t("providers.test.replaceFail")}
              />
              {replace.error != null ? (
                <p role="alert" className="text-sm text-danger">
                  {translateApiError(t, replace.error)}
                </p>
              ) : null}
            </>
          )}
        </div>
        <DialogFooter>
          {waiting ? (
            <>
              <Button variant="ghost" onClick={onClose}>
                {t("common.done")}
              </Button>
              <Button onClick={openApprovalsSheet}>{t("providers.key.review")}</Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose}>
                {t("common.cancel")}
              </Button>
              <Button disabled={!secret || replace.isPending} onClick={() => void submit()}>
                {t("providers.key.replace")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
