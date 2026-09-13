// frontend/src/pages/settings/DaemonPortCard.tsx
//
// Settings → General → the address this UI is served at, and the port behind
// it (spec mcp-gateway FR-028). The bookmark address comes first because it is
// the whole reason the setting exists: with no fixed port the daemon takes the
// first free one in a small range, so a bookmark dies the moment the port
// drifts.
//
// Auto-save, like every other settings card: a Save button here taught the
// page two rules at once, and made the controls above it — which save the
// moment you change them — read as unsaved. The switch writes on toggle (each
// position is a complete answer); the number field writes when you leave it,
// because a half-typed port is a valid number the instant you pause ("80" on
// the way to "8080") and this setting decides whether the daemon can bind at
// all on its next start.
//
// There is no "restart now" button on purpose: this page is served BY the
// daemon, so restarting it from the browser would kill the server answering
// the request. The note names the command instead.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { MAX_PORT, MIN_PORT } from "@/lib/api/daemonSettings";
import { translateApiError } from "@/lib/api/errors";
import { useDaemonSettings, useUpdateDaemonPort } from "@/lib/hooks/useDaemonSettings";

const RESTART_COMMAND = "coffer daemon restart";

export function DaemonPortCard() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const query = useDaemonSettings();
  const update = useUpdateDaemonPort();

  // The mutation's echo is the freshest truth (the invalidated query is still
  // in flight right after a save), so it wins where both have an answer.
  const settings = update.data ?? query.data;
  const effectivePort = settings?.effective_port ?? null;
  const configuredPort = query.data?.configured_port ?? null;

  const [fixed, setFixed] = useState(false);
  const [portText, setPortText] = useState("");
  const [rangeError, setRangeError] = useState(false);
  const [copied, setCopied] = useState(false);

  // Seed the form from the daemon's answer (and re-seed after each save).
  // Primitive dependencies, so this follows the values rather than the
  // identity of whatever object a refetch hands back.
  useEffect(() => {
    if (effectivePort === null) return;
    setFixed(configuredPort !== null);
    setPortText(String(configuredPort ?? effectivePort));
  }, [configuredPort, effectivePort]);

  const address = effectivePort === null ? null : `http://127.0.0.1:${effectivePort}`;

  const copy = () => {
    if (!address) return;
    void navigator.clipboard.writeText(address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const toggle = (checked: boolean) => {
    setFixed(checked);
    setRangeError(false);
    if (!checked) {
      update.mutate(null, { onSuccess: announce });
      return;
    }
    // Turning it on defaults to the port that is already serving this page —
    // the one setting guaranteed not to break the address shown above, so it
    // is safe to write straight away.
    if (effectivePort === null) return;
    setPortText(String(effectivePort));
    update.mutate(effectivePort, { onSuccess: announce });
  };

  // A restart-pending save gets the persistent note below instead of a toast
  // that vanishes before it has been read.
  const announce = (result: { restart_required: boolean }) => {
    if (!result.restart_required) toast.success(t("settings.daemonPort.saved"));
  };

  // The number field commits when the user leaves it (or presses Enter), never
  // per keystroke: on the way to 8123 the field reads 8, 81 and 812, each a
  // number the daemon would happily bind to.
  const commitPort = () => {
    setRangeError(false);
    const port = Number(portText.trim());
    if (!Number.isInteger(port) || port < MIN_PORT || port > MAX_PORT) {
      setRangeError(true);
      return;
    }
    if (port === configuredPort) return;
    update.mutate(port, { onSuccess: announce });
  };

  const restartRequired = settings?.restart_required ?? false;
  const error = query.error ?? update.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.daemonPort.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("settings.daemonPort.description")}</p>

        <div className="space-y-2 rounded-lg border border-primary/30 bg-accent/30 p-3">
          <Label className="text-xs text-muted-foreground">
            {t("settings.daemonPort.address")}
          </Label>
          <div className="flex flex-wrap items-center gap-2">
            <code className="break-all text-sm" data-testid="daemon-address">
              {address ?? "—"}
            </code>
            <Button
              size="sm"
              variant="outline"
              onClick={copy}
              disabled={!address}
              aria-label={t("settings.daemonPort.copy")}
            >
              <Copy className="mr-1.5 size-3.5" />
              {copied ? t("settings.daemonPort.copied") : t("settings.daemonPort.copy")}
            </Button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="daemon-fixed-port">{t("settings.daemonPort.useFixed")}</Label>
          <Switch
            id="daemon-fixed-port"
            checked={fixed}
            disabled={update.isPending}
            onCheckedChange={toggle}
          />
        </div>
        <p className="text-xs text-muted-foreground">{t("settings.daemonPort.useFixedHint")}</p>

        {fixed && (
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="daemon-port">{t("settings.daemonPort.port")}</Label>
            <Input
              id="daemon-port"
              type="number"
              className="w-44"
              min={MIN_PORT}
              max={MAX_PORT}
              value={portText}
              disabled={update.isPending}
              onChange={(e) => setPortText(e.target.value)}
              onBlur={commitPort}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitPort();
              }}
            />
          </div>
        )}

        {rangeError && (
          <p className="text-xs text-destructive" role="alert">
            {t("settings.daemonPort.rangeError", { min: MIN_PORT, max: MAX_PORT })}
          </p>
        )}

        {error && !rangeError && (
          <p className="text-xs text-destructive" role="alert">
            {translateApiError(t, error)}
          </p>
        )}

        {restartRequired && (
          <Alert data-testid="daemon-restart-note">
            <AlertTitle>{t("settings.daemonPort.restartTitle")}</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{t("settings.daemonPort.restartBody")}</p>
              <code className="block text-sm">{RESTART_COMMAND}</code>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
