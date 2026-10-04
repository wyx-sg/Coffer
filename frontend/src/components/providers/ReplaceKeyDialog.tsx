// src/components/providers/ReplaceKeyDialog.tsx — replace the value behind a provider's secret, tested first.
//
// The pasted key is checked as it arrives (no Test button): the endpoint's
// models are listed with the NEW key inline, before anything is written. Replace PATCHes `secret_value`: the daemon overwrites the value
// behind the same ref at once (the agents' config files only name the ref, so
// they do not change).
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

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
import { useReplaceProviderKey } from "@/lib/hooks/useProviders";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ProbeResult } from "./ProbeResult";
import { useEndpointTest } from "./useEndpointTest";
import { useUserNames } from "./useUserNames";
import { secretReferenceOf } from "@/lib/secretValue";

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
  const users = useUserNames(use);
  const [secret, setSecret] = useState("");

  useEffect(() => {
    if (!open) return;
    setSecret("");
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

  const submit = async () => {
    try {
      await replace.mutateAsync({ uid: provider.uid, secret });
    } catch {
      return; // rendered inline below
    }
    onClose();
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
              <span className="font-mono text-xs">
                {provider.secret_ref ? secretReferenceOf(provider.secret_ref) : null}
              </span>
            </span>
          </div>
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
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!secret || replace.isPending} onClick={() => void submit()}>
            {t("providers.key.replace")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
