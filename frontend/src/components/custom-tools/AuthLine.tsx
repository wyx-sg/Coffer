// src/components/custom-tools/AuthLine.tsx — how a group header reads: its name, an arrow, and the secret its whole
// value comes from as a chip ("Authorization ← [🔑 deploy-token]"). No prefix: the secret is the whole value.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { SecretName, SecretNameLink } from "@/components/secret/SecretNameLink";

interface Props {
  header: string;
  secret: string;
  /** After the chip: "from the group". */
  trailing?: ReactNode;
  /** Inside a form or drawer where following the link would lose work: the name as plain text. */
  plain?: boolean;
}

export function AuthLine({ header, secret, trailing, plain = false }: Props) {
  const { t } = useTranslation();
  const ref = secret.startsWith("secret/") ? secret : `secret/${secret}`;
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2 text-sm">
      <span className="font-mono text-xs text-text">{header}</span>
      <span className="text-xs text-text-subtle" role="img" aria-label={t("secretRows.readsFrom")}>
        ←
      </span>
      <span className="inline-flex h-[22px] items-center gap-1.5 rounded-md border border-border-subtle bg-surface-sunken px-[7px] text-xs text-text">
        <KeyRound className="size-3 text-text-muted" aria-hidden />
        {plain ? (
          <SecretName secretRef={ref} />
        ) : (
          <SecretNameLink secretRef={ref} className="text-xs" />
        )}
      </span>
      {trailing}
    </span>
  );
}
