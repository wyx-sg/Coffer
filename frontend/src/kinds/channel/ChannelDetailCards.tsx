// frontend/src/kinds/channel/ChannelDetailCards.tsx
// The detail-page cards: live status (adapter + paired peer), pairing
// (generate / show a code), the SeaTalk callback endpoint, and a "send test
// message" card wired to the notify capability. Kept out of ChannelDetailPage
// so the page stays within the size budget.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, KeyRound, Webhook, Activity, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CallbackInfo, ChannelStatus, PairingCode } from "@/lib/api/channels";

function StatusRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}

/** Adapter run state + the paired peer (or "not paired"). */
export function ChannelStatusCard({ status }: { status: ChannelStatus | undefined }) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Activity className="size-4 text-primary" aria-hidden />
          {t("channels.status.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {status === undefined ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          <>
            <StatusRow
              label={t("channels.status.adapter")}
              value={
                status.running ? (
                  <Badge>{t("channels.status.running")}</Badge>
                ) : (
                  <Badge variant="outline">{t("channels.status.stopped")}</Badge>
                )
              }
            />
            {status.peer === null ? (
              <StatusRow
                label={t("channels.status.peer")}
                value={<span className="text-muted-foreground">{t("channels.notPaired")}</span>}
              />
            ) : (
              <>
                <StatusRow
                  label={t("channels.status.peer")}
                  value={<span className="font-medium">{status.peer.display_name}</span>}
                />
                <StatusRow
                  label={t("channels.status.chatId")}
                  value={<code className="text-xs">{status.peer.chat_id}</code>}
                />
                <StatusRow
                  label={t("channels.status.pairedAt")}
                  value={new Date(status.peer.paired_at).toLocaleString()}
                />
                <StatusRow
                  label={t("channels.status.conversation")}
                  value={
                    status.peer.active_conversation_id !== null ? (
                      <code className="text-xs">{status.peer.active_conversation_id}</code>
                    ) : (
                      <span className="text-muted-foreground">{t("channels.status.none")}</span>
                    )
                  }
                />
              </>
            )}
            {status.pending_pairing ? (
              <p className="pt-1 text-xs text-muted-foreground">
                {t("channels.status.pendingPairing")}
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Generate-pairing-code button + the LARGE code with expiry and copy. */
export function ChannelPairingCard({
  code,
  isPending,
  onGenerate,
}: {
  code: PairingCode | undefined;
  isPending: boolean;
  onGenerate: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = () => {
    if (!code) return;
    void navigator.clipboard.writeText(code.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <KeyRound className="size-4 text-primary" aria-hidden />
          {t("channels.pairing.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="max-w-prose text-sm text-muted-foreground">
          {t("channels.pairing.instruction")}
        </p>
        <Button onClick={onGenerate} disabled={isPending}>
          {isPending ? t("channels.pairing.generating") : t("channels.pairing.generate")}
        </Button>
        {code ? (
          <div className="space-y-2 rounded-lg border border-primary/30 bg-accent/30 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-4xl font-semibold tracking-[0.3em]">{code.code}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={copy}
                aria-label={t("channels.pairing.copy")}
              >
                <Copy className="mr-1.5 size-3.5" />
                {copied ? t("channels.pairing.copied") : t("channels.pairing.copy")}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {t("channels.pairing.expires", {
                time: new Date(code.expires_at).toLocaleTimeString(),
              })}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** SeaTalk only: where the callback listener serves, and the tunnel hint. */
export function ChannelCallbackCard({ callback }: { callback: CallbackInfo }) {
  const { t } = useTranslation();
  const endpoint = `127.0.0.1:${callback.port}${callback.path}`;
  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Webhook className="size-4 text-primary" aria-hidden />
          {t("channels.callback.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
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

/**
 * Send a one-off message to the paired peer via the notify capability — the
 * live-verification path for a freshly paired channel. Disabled until a peer
 * exists (there is nobody to notify before pairing).
 */
export function ChannelTestMessageCard({
  hasPeer,
  isPending,
  onSend,
}: {
  hasPeer: boolean;
  isPending: boolean;
  onSend: (text: string) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const trimmed = text.trim();

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Send className="size-4 text-primary" aria-hidden />
          {t("channels.test.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="max-w-prose text-sm text-muted-foreground">{t("channels.test.subtitle")}</p>
        <div className="space-y-2">
          <Label htmlFor="channel-test-message">{t("channels.test.title")}</Label>
          <Input
            id="channel-test-message"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("channels.test.placeholder")}
            disabled={!hasPeer || isPending}
          />
        </div>
        <Button
          onClick={() => onSend(trimmed)}
          disabled={!hasPeer || isPending || trimmed.length === 0}
        >
          {isPending ? t("channels.test.sending") : t("channels.test.send")}
        </Button>
        {!hasPeer ? (
          <p className="text-xs text-muted-foreground">{t("channels.test.needsPeer")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
