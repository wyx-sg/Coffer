// src/components/chat/ChannelMirrorHint.tsx
// The one quiet line above the composer of a channel conversation: where a
// reply typed here also goes, or that it stays in Coffer and why (spec chat
// "Show where a reply will also be sent").
import { useTranslation } from "react-i18next";

import type { ChannelMirror } from "@/lib/api/chat";
import { HelpTip } from "@/components/HelpTip";

/** The reasons the daemon gives for a reply that stays in Coffer. */
const REASONS = new Set(["group_main", "not_located", "chat_kind_unknown", "channel_deleted"]);

interface Props {
  mirror: ChannelMirror;
}

export function ChannelMirrorHint({ mirror }: Props) {
  const { t } = useTranslation();
  const reason = mirror.reason && REASONS.has(mirror.reason) ? mirror.reason : "not_located";
  return (
    <div className="mx-auto flex w-full max-w-[calc(720px+4rem)] items-center gap-0.5 px-8 pt-2 text-xs text-text-muted">
      {mirror.deliverable ? (
        <span>{t("conversations.mirror.alsoSends", { target: mirror.target })}</span>
      ) : (
        <>
          <span>{t("conversations.mirror.staysInCoffer")}</span>
          <HelpTip>
            <p className="text-sm">{t(`conversations.mirror.reason.${reason}`)}</p>
          </HelpTip>
        </>
      )}
    </div>
  );
}
