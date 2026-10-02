// frontend/src/components/channel/ChannelPeopleDialogs.tsx
// The confirmation behind a row of "Who can use it": Remove (un-pair them).
// The pane owns whether it is open and who it is about; this renders it.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { ChannelPerson } from "@/lib/api/channels";

interface Props {
  dialog: "remove" | null;
  onOpenChange: (open: boolean) => void;
  channelName: string;
  target: ChannelPerson | null;
  /** The target is the only paired owner — removing them leaves nobody paired. */
  isLastOwner: boolean;
  removePending: boolean;
  onRemove: (senderId: string) => void | Promise<unknown>;
}

export function ChannelPeopleDialogs({
  dialog,
  onOpenChange,
  channelName,
  target,
  isLastOwner,
  removePending,
  onRemove,
}: Props) {
  const { t } = useTranslation();
  const owner = target?.display_name ?? "";
  return (
    <>
      <ConfirmDialog
        open={dialog === "remove"}
        onOpenChange={onOpenChange}
        title={t("channels.removePerson.title", { name: channelName, owner })}
        description={t(
          isLastOwner ? "channels.removePerson.bodyLast" : "channels.removePerson.body",
          { owner },
        )}
        confirmLabel={t("channels.removePerson.confirm")}
        pending={removePending}
        onConfirm={() => onRemove(target?.sender_id ?? "")}
      />
    </>
  );
}
