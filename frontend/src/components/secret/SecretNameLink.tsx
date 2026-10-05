// src/components/secret/SecretNameLink.tsx — a secret a resource uses, shown by its readable name.
//
// Wherever a pane says which secret a provider, server or remote uses, it shows the secret's
// name (spec web-ui "Manage stored secrets on the Secrets page"), never its `secret/<id>` ref or
// `coffer://` URI. The name opens that secret's own page in the Secrets split view.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { displayName } from "./secretRows";

/** What a ref is called: its display name; "Unnamed secret" while the list loads or lacks it. */
export function useSecretName(ref: string): string {
  const { t } = useTranslation();
  const { data } = useSecrets();
  const row = data?.refs.find((r) => r.ref === ref);
  return row ? displayName(row, t("secrets.unnamed")) : t("secrets.unnamed");
}

const LINK = "font-label text-accent-text no-underline hover:underline";

/** The name as plain text, for a sentence or a dialog that must not navigate. */
export function SecretName({ secretRef }: { secretRef: string }) {
  return <>{useSecretName(secretRef)}</>;
}

interface LinkProps {
  secretRef: string;
  className?: string;
  /** Called when the link is followed — a dialog closes itself here. */
  onNavigate?: () => void;
}

export function SecretNameLink({ secretRef, className, onNavigate }: LinkProps) {
  const name = useSecretName(secretRef);
  return (
    <Link
      to={`/secrets/${encodeURIComponent(secretRef)}`}
      className={cn(LINK, className)}
      onClick={onNavigate}
    >
      {name}
    </Link>
  );
}
