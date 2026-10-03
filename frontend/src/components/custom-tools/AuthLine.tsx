// src/components/custom-tools/AuthLine.tsx — how a group header reads: its name, an arrow, and the secret its whole
// value comes from as a chip ("Authorization ← [🔑 deploy-token]"). No prefix: the secret is the whole value.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

interface Props {
  header: string;
  secret: string;
  /** After the chip: "from the group". */
  trailing?: ReactNode;
}

export function AuthLine({ header, secret, trailing }: Props) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2 text-sm">
      <span className="font-mono text-xs text-text">{header}</span>
      <span className="text-xs text-text-subtle" role="img" aria-label={t("secretRows.readsFrom")}>
        ←
      </span>
      <span className="inline-flex h-[22px] items-center gap-1.5 rounded-md border border-border-subtle bg-surface-sunken px-[7px] font-mono text-xs text-text">
        <KeyRound className="size-3 text-text-muted" aria-hidden />
        {secret}
      </span>
      {trailing}
    </span>
  );
}
