// src/components/providers/ReplaceKeyDialog.tsx — Replace API key: the one Replace dialog, with the key checked as it is pasted.
//
// The pasted key is checked as it arrives (no Test button): the endpoint's
// models are listed with the NEW key inline, before anything is written. Replace PATCHes `secret_value`: the daemon overwrites the value
// behind the same ref at once (the agents' config files only name the ref, so
// they do not change). "Use another secret" PATCHes `secret_ref` instead and
// skips the check: a stored key is probed only for the connection that holds it.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Provider } from "@/lib/api/providers";
import { useRebindProviderKey, useReplaceProviderKey } from "@/lib/hooks/useProviders";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { EMPTY_DRAFT, type ReplaceDraft } from "@/components/secret/ReplaceSecretFields";
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
  const replaceValue = useReplaceProviderKey();
  const rebind = useRebindProviderKey();
  const test = useEndpointTest(t);
  const users = useUserNames(use);
  const [draft, setDraft] = useState<ReplaceDraft>(EMPTY_DRAFT);

  useEffect(() => {
    if (open) test.reset();
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Check the key once the paste settles: nothing is written by a check.
  const runTest = useRef(test.run);
  runTest.current = test.run;
  const pasted = draft.source === "value" ? draft.value : "";
  useEffect(() => {
    if (!open || !pasted) return;
    const timer = setTimeout(() => {
      void runTest.current({
        provider: provider.protocol,
        base_url: provider.base_url,
        secret_value: pasted,
      });
    }, 500);
    return () => clearTimeout(timer);
  }, [open, pasted, provider.protocol, provider.base_url]);

  return (
    <ReplaceSecretDialog
      secretRef={open ? provider.secret_ref : null}
      onClose={onClose}
      field={t("providers.fields.apiKey")}
      draft={draft}
      onDraftChange={(next) => {
        if (next.value !== draft.value || next.source !== draft.source) test.reset();
        setDraft(next);
      }}
      onReplaceValue={(secret) => replaceValue.mutateAsync({ uid: provider.uid, secret })}
      onRebind={(secretRef) => rebind.mutateAsync({ uid: provider.uid, secretRef })}
      check={
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
      }
    />
  );
}
