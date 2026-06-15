// frontend/src/kinds/channel/ChannelCallbackCard.tsx
// SeaTalk-only detail card: the public callback URL to register on the SeaTalk
// Open Platform (composed once the owner records their tunnel's base URL), a
// reachability self-test, the local listener address, and the tunnel hint.
// Split out of ChannelDetailCards to keep each within the size budget.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Webhook } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import type { CallbackInfo, CallbackTestResult } from "@/lib/api/channels";
import { testChannelCallback } from "@/lib/api/channels";
import { translateApiError } from "@/lib/api/errors";
import { StatusRow } from "./ChannelDetailCards";

export function ChannelCallbackCard({ name, callback }: { name: string; callback: CallbackInfo }) {
  const { t } = useTranslation();
  const endpoint = `127.0.0.1:${callback.port}${callback.path}`;
  const [copied, setCopied] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<CallbackTestResult | null>(null);

  const copy = () => {
    if (!callback.public_callback_url) return;
    void navigator.clipboard.writeText(callback.public_callback_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const runTest = () => {
    setTesting(true);
    setTestResult(null);
    void testChannelCallback(name)
      .then((r) => setTestResult(r))
      .catch((e) => setTestResult({ ok: false, detail: translateApiError(t, e) }))
      .finally(() => setTesting(false));
  };

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Webhook className="size-4 text-primary" aria-hidden />
          {t("channels.callback.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {callback.public_callback_url ? (
          <div className="space-y-2 rounded-lg border border-primary/30 bg-accent/30 p-3">
            <Label className="text-xs text-muted-foreground">
              {t("channels.callback.registerUrl")}
            </Label>
            <div className="flex flex-wrap items-center gap-2">
              <code className="break-all text-sm">{callback.public_callback_url}</code>
              <Button
                size="sm"
                variant="outline"
                onClick={copy}
                aria-label={t("channels.callback.copy")}
              >
                <Copy className="mr-1.5 size-3.5" />
                {copied ? t("channels.callback.copied") : t("channels.callback.copy")}
              </Button>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button size="sm" variant="outline" onClick={runTest} disabled={testing}>
                {testing ? t("channels.callback.testing") : t("channels.callback.test")}
              </Button>
              {testResult ? (
                <span
                  className={`text-xs ${testResult.ok ? "text-primary" : "text-destructive"}`}
                  role="status"
                >
                  {testResult.ok ? "✓ " : "✗ "}
                  {testResult.detail}
                </span>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">{t("channels.callback.setBaseUrlHint")}</p>
        )}
        <StatusRow
          label={t("channels.callback.endpoint")}
          value={<code className="text-xs">{endpoint}</code>}
        />
        <StatusRow
          label={t("channels.callback.listener")}
          value={
            callback.listener_running ? (
              <Badge>{t("channels.status.running")}</Badge>
            ) : (
              <Badge variant="outline">{t("channels.status.stopped")}</Badge>
            )
          }
        />
        <p className="pt-1 text-xs text-muted-foreground">{t("channels.callback.hint")}</p>
      </CardContent>
    </Card>
  );
}
