// src/components/settings/security/AccessTokenRow.tsx — the daemon access token on Settings › Security.
//
// The one place in the web UI that shows the token (spec web-ui "Show, copy
// and rotate the access token on Settings › Security"): masked until Show,
// Copy to the clipboard, and Rotate behind a confirmation. Show is a plain
// unmask — the token is already in this page, it is what every request
// carries — so it asks for no presence check.
//
// Rotating installs the returned token before the dialog closes, so the page
// carries on with no reload; a failed rotation keeps the dialog open with the
// error, and the old token stays the one in use. While the daemon cannot be
// reached every control is disabled — a rotation then could only fail.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { getCofferToken } from "@/lib/auth";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useRotateDaemonToken } from "@/lib/hooks/useSecurity";

import { SettingRow } from "@/components/settings/SettingsLayout";

/** Where the daemon publishes its token — shown, never read, by the page. */
const TOKEN_FILE = "~/.coffer/daemon.json";

/** Dots and the last four characters: enough to tell two tokens apart. */
function maskToken(token: string): string {
  return `${"•".repeat(12)}${token.slice(-4)}`;
}

export function AccessTokenRow() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { isError: unreachable } = useDaemonStatus();
  const rotate = useRotateDaemonToken();
  const [token, setToken] = useState(getCofferToken);
  const [shown, setShown] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const disabled = unreachable || token === null;

  const copy = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      toast.success(t("common.copied"));
    } catch {
      toast.error(t("settings.security.token.copyFailed"));
    }
  };

  return (
    <SettingRow
      label={t("settings.security.token.title")}
      description={t("settings.security.token.description")}
    >
      <code
        className="flex h-control-md w-48 items-center truncate rounded-md border border-border bg-surface-raised px-2.5 font-mono text-xs text-text"
        data-testid="daemon-token"
      >
        {token === null ? t("settings.security.token.none") : shown ? token : maskToken(token)}
      </code>
      <Button variant="outline" disabled={disabled} onClick={() => setShown((s) => !s)}>
        {shown ? t("settings.security.token.hide") : t("settings.security.token.show")}
      </Button>
      <Button variant="outline" disabled={disabled} onClick={() => void copy()}>
        <Copy aria-hidden />
        {t("settings.security.token.copy")}
      </Button>
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => {
          rotate.reset();
          setConfirming(true);
        }}
      >
        <RefreshCw aria-hidden />
        {t("settings.security.token.rotate")}
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("settings.security.token.rotateTitle")}
        description={t("settings.security.token.rotateBody")}
        confirmLabel={
          rotate.isPending
            ? t("settings.security.token.rotating")
            : t("settings.security.token.rotateConfirm")
        }
        variant="default"
        pending={rotate.isPending}
        error={rotate.error}
        onConfirm={() =>
          rotate.mutate(undefined, {
            onSuccess: (next) => {
              setToken(next);
              setConfirming(false);
              toast.success(t("settings.security.token.rotated"));
            },
          })
        }
      >
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg bg-surface-sunken px-3 py-2 text-xs">
          <dt className="text-text-muted">{t("settings.security.token.tokenFile")}</dt>
          <dd className="font-mono text-text">{TOKEN_FILE}</dd>
        </dl>
        <p className="text-xs text-text-muted">{t("settings.security.token.recorded")}</p>
      </ConfirmDialog>
    </SettingRow>
  );
}
