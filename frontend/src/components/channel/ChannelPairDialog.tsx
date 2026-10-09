// frontend/src/components/channel/ChannelPairDialog.tsx
// The whole "add an owner" flow in one dialog: what will happen, the pairing
// code (requested as the dialog opens), the platform's instruction, a live
// waiting line, and — once somebody pairs — who. Dismissing it without a
// pairing (Cancel on an expired code, Esc, the ×, a click outside) withdraws
// the outstanding code; Done leaves a code the person may already have sent.
// Used for the first pairing and Add owner; the page itself prints nothing of
// this.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { PairingCode } from "@/lib/api/channels";
import { useCancelPairingCode, useIssuePairingCode } from "@/lib/hooks/useChannelPairing";
import { useChannelStatus } from "@/lib/hooks/useChannels";
import { ChannelPairingCode } from "./ChannelPairingCode";
import { usePairingExpired } from "./pairingCode";

interface Props {
  uid: string;
  platform: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChannelPairDialog({ open, onOpenChange, ...rest }: Props) {
  // Mounted only while open: opening is what requests the code.
  return open ? <PairDialogBody onClose={() => onOpenChange(false)} {...rest} /> : null;
}

function PairDialogBody({
  uid,
  platform,
  onClose,
}: Omit<Props, "open" | "onOpenChange"> & { onClose: () => void }) {
  const { t } = useTranslation();
  const issuePairing = useIssuePairingCode(uid);
  const cancelPairing = useCancelPairingCode(uid);
  const { data: status } = useChannelStatus(uid, { poll: true });
  const [code, setCode] = useState<PairingCode | undefined>(undefined);
  const [issuing, setIssuing] = useState(false);
  const [issuedAt, setIssuedAt] = useState(0);
  const started = useRef(false);
  const { mutateAsync } = issuePairing;
  const expired = usePairingExpired(code);

  const issue = useCallback(() => {
    setIssuing(true);
    setIssuedAt(Date.now());
    // A refusal is toasted by the hook; the dialog then offers Generate again.
    mutateAsync()
      .then(setCode, () => undefined)
      .finally(() => setIssuing(false));
  }, [mutateAsync]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    issue();
  }, [issue]);

  // A code is spent once somebody paired after it was issued.
  const paired =
    code === undefined
      ? undefined
      : status?.people.find((p) => new Date(p.paired_at).getTime() >= issuedAt - 5_000);

  const dismiss = () => {
    if (code && !paired) cancelPairing.mutate();
    onClose();
  };

  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : dismiss())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("channels.pair.title")}</DialogTitle>
          <DialogDescription>{t("channels.pair.intro")}</DialogDescription>
        </DialogHeader>
        {paired ? (
          <div className="flex gap-2.5 rounded-xl bg-success-soft p-3.5" data-testid="pair-success">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            <p className="text-sm font-label text-text">
              {t("channels.pair.added", { owner: paired.display_name })}
            </p>
          </div>
        ) : (
          <ChannelPairingCode
            platform={platform}
            channelName={status ? status.name : ""}
            code={code}
            expired={expired}
            isPending={issuing}
            onGenerate={issue}
          />
        )}
        <DialogFooter>
          {paired ? (
            <Button onClick={onClose}>{t("common.done")}</Button>
          ) : expired ? (
            <>
              <Button variant="ghost" onClick={dismiss}>
                {t("common.cancel")}
              </Button>
              <Button onClick={issue} disabled={issuing}>
                {t("channels.pairing.newCodeAfterExpiry")}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={issue} disabled={issuing || code === undefined}>
                {t("channels.pairing.newCode")}
              </Button>
              <Button variant="outline" onClick={onClose}>
                {t("common.done")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
