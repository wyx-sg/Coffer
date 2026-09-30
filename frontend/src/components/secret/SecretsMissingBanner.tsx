// src/components/secret/SecretsMissingBanner.tsx — "N secrets have no value on this Mac", with Import master key….
//
// A secret the vault cites but this Mac cannot hand out — never stored here,
// or stored under another Mac's master key (encrypted secrets don't sync by
// default) — leaves whatever uses it unable to start. The banner counts them
// and opens Settings › Security, where the master key from the other Mac is
// imported (spec secret "Show a secret this Mac cannot open as missing on
// this Mac"). Each row still offers Add value on its own.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export function SecretsMissingBanner({ count }: { count: number }) {
  const { t } = useTranslation();
  if (count === 0) return null;
  return (
    <div
      role="status"
      data-testid="secrets-missing-banner"
      className="flex items-center gap-3 rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-2.5"
    >
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-semibold text-text">{t("secrets.missing.title", { count })}</p>
        <p className="text-xs text-text-muted">{t("secrets.missing.body")}</p>
      </div>
      <Button asChild variant="outline" size="sm" className="ml-auto">
        <Link to="/settings/security">{t("secrets.missing.importKey")}</Link>
      </Button>
    </div>
  );
}
