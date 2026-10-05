// src/components/secret/SecretRefControl.tsx — the one way a pane shows a secret a resource uses.
//
// The secret's readable name, linking to its page on the Secrets page, and
// "Replace key…" beside it, which opens the resource's replace dialog in place
// (a new value for this secret, or another stored secret instead).
import type { ReactNode } from "react";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { SecretNameLink } from "./SecretNameLink";

interface Props {
  secretRef: string;
  /** Opens the replace dialog; omitted, only the name is shown. */
  onReplace?: () => void;
  /** Shown between the name and the button — a status word such as Rejected. */
  status?: ReactNode;
  className?: string;
}

export function SecretRefControl({ secretRef, onReplace, status, className }: Props) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-3", className)}>
      <SecretNameLink secretRef={secretRef} className="max-w-[260px] truncate text-sm" />
      {status}
      {onReplace ? (
        <Button variant="outline" size="sm" onClick={onReplace}>
          <KeyRound aria-hidden /> {t("secretRef.replaceOpen")}
        </Button>
      ) : null}
    </span>
  );
}
