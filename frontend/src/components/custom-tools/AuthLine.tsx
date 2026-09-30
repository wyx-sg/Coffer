// src/components/custom-tools/AuthLine.tsx — how a group's auth reads: the header, an arrow, and the
// secret its value comes from as a chip ("Authorization: Bearer ← secret [deploy-token]").
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, KeyRound } from "lucide-react";

import { authLine } from "@/lib/customTools/drafts";

interface Props {
  header: string;
  prefix: string;
  secret: string;
  /** After the chip: "from the group", a Missing badge. */
  trailing?: ReactNode;
}

export function AuthLine({ header, prefix, secret, trailing }: Props) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2 text-sm">
      <span className="font-mono text-xs text-text">{authLine(header, prefix)}</span>
      <span className="inline-flex items-center gap-1 text-xs text-text-muted">
        <ArrowLeft className="size-3" aria-hidden />
        {t("customTools.definition.secretWord")}
      </span>
      <span className="inline-flex h-control-sm items-center gap-1.5 rounded-md border border-border-subtle bg-surface-raised px-2 font-mono text-xs text-text">
        <KeyRound className="size-3 text-text-muted" aria-hidden />
        {secret}
      </span>
      {trailing}
    </span>
  );
}
