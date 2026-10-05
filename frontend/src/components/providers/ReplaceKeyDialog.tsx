// src/components/providers/ReplaceKeyDialog.tsx — replace the value behind a provider's secret, tested first.
//
// The pasted key is checked as it arrives (no Test button): the endpoint's
// models are listed with the NEW key inline, before anything is written. Replace PATCHes `secret_value`: the daemon overwrites the value
// behind the same ref at once (the agents' config files only name the ref, so
// they do not change). "Use another secret" PATCHes `secret_ref` instead and
// skips the check: a stored key is probed only for the connection that holds it.
import { useEffect, useRef, useState } from "react";
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
import { useRebindProviderKey, useReplaceProviderKey } from "@/lib/hooks/useProviders";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ProbeResult } from "./ProbeResult";
import { useEndpointTest } from "./useEndpointTest";
import { useUserNames } from "./useUserNames";
import { SecretNameLink } from "@/components/secret/SecretNameLink";
import { SecretSourceSwitch, type SecretSource } from "@/components/secret/SecretSourceSwitch";

interface Props {
  open: boolean;
  provider: Provider;
  use: ProviderUse;
  onClose: () => void;
}

export function ReplaceKeyDialog({ open, provider, use, onClose }: Props) {
  const { t } = useTranslation();
  const replaceValue = useReplaceProviderKey();
  const rebind = useRebindProviderKey();
  const test = useEndpointTest(t);
  const users = useUserNames(use);
  const [secret, setSecret] = useState("");
  const [source, setSource] = useState<SecretSource>("value");
  const [picked, setPicked] = useState("");
  const replace = source === "value" ? replaceValue : rebind;

  useEffect(() => {
    if (!open) return;
    setSecret("");
    setSource("value");
    setPicked("");
    test.reset();
    replaceValue.reset();
    rebind.reset();
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Check the key once the paste settles: nothing is written by a check.
  const runTest = useRef(test.run);
  runTest.current = test.run;
  useEffect(() => {
    if (!open || source !== "value" || !secret) return;
    const timer = setTimeout(() => {
      void runTest.current({
        provider: provider.protocol,
        base_url: provider.base_url,
        secret_value: secret,
      });
    }, 500);
    return () => clearTimeout(timer);
  }, [open, source, secret, provider.protocol, provider.base_url]);

  const submit = async () => {
    try {
      if (source === "value") {
        await replaceValue.mutateAsync({ uid: provider.uid, secret });
      } else {
        await rebind.mutateAsync({ uid: provider.uid, secretRef: picked });
      }
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
              {provider.secret_ref ? (
                <SecretNameLink
                  secretRef={provider.secret_ref}
                  className="text-xs"
                  onNavigate={onClose}
                />
              ) : null}
            </span>
          </div>
          {provider.secret_ref ? (
            <SecretSourceSwitch
              source={source}
              onSourceChange={(next) => {
                setSource(next);
                test.reset();
              }}
              currentRef={provider.secret_ref}
              picked={picked}
              onPick={setPicked}
              disabled={replace.isPending}
            />
          ) : null}
          {source === "value" ? (
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
              <p className="text-xs text-text-muted">{t("providers.replace.hint")}</p>
            </div>
          ) : null}
          {source === "value" ? (
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
          ) : null}
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
          <Button
            disabled={(source === "value" ? !secret : !picked) || replace.isPending}
            onClick={() => void submit()}
          >
            {source === "value" ? t("providers.key.replace") : t("secretRef.useSubmit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
