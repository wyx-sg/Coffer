// frontend/src/components/channel/ChannelSendTestDialog.tsx
// "Send a test message": the live check that delivery works. The message is
// prefilled and editable; it goes to the paired owner's direct chat through
// the notify capability, and starts no turn. Closes only once it is sent.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useNotifyChannel } from "@/lib/hooks/useChannels";

interface Props {
  uid: string;
  owner: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChannelSendTestDialog({ uid, owner, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const notify = useNotifyChannel(uid);
  const [text, setText] = useState(() => t("channels.test.fixedMessage"));
  useEffect(() => {
    if (open) setText(t("channels.test.fixedMessage"));
  }, [open, t]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("channels.test.title")}</DialogTitle>
          <DialogDescription>{t("channels.test.goesTo", { owner })}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor={id}>{t("channels.test.message")}</Label>
          <Textarea id={id} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={notify.isPending || text.trim() === ""}
            onClick={() => notify.mutate(text.trim(), { onSuccess: () => onOpenChange(false) })}
          >
            {notify.isPending ? t("channels.test.sending") : t("channels.test.send")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
