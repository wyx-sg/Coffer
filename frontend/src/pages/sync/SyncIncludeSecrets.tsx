// frontend/src/pages/sync/SyncIncludeSecrets.tsx
//
// "Include encrypted secrets": whether this Mac's secrets travel to the
// remote as ciphertext. Turning it ON on a stored remote asks first (board
// 6.5.23), naming the repository and how many secrets that is, because from
// the next round everyone with access to the repository sees that they exist
// and what they are called. The master key never leaves this Mac. Turning it
// off needs no question: nothing more is pushed.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";

interface Props {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Ask before turning it on — true once the remote is stored. */
  confirm: boolean;
  /** How many encrypted secrets this vault holds. */
  secrets: number;
  url: string;
  disabled?: boolean;
  describedBy?: string;
}

export function SyncIncludeSecrets({
  id,
  checked,
  onChange,
  confirm,
  secrets,
  url,
  disabled,
  describedBy,
}: Props) {
  const { t } = useTranslation();
  const [asking, setAsking] = useState(false);

  return (
    <>
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        aria-describedby={describedBy}
        onCheckedChange={(next) => (next && confirm ? setAsking(true) : onChange(next))}
      />
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        variant="default"
        title={t("sync.remote.secretsOn.title")}
        description={t("sync.remote.secretsOn.lead", { url })}
        confirmLabel={t("sync.remote.secretsOn.confirm")}
        onConfirm={() => {
          onChange(true);
          setAsking(false);
        }}
      >
        <div className="flex flex-col gap-2 rounded-lg border border-border-subtle px-3.5 py-3 text-sm">
          <p className="font-label text-text">
            {t("sync.remote.secretsOn.count", { count: secrets })}
          </p>
          <p className="text-xs text-text-muted">{t("sync.remote.secretsOn.key")}</p>
          <p className="text-xs text-text-muted">{t("sync.remote.secretsOn.visible")}</p>
        </div>
      </ConfirmDialog>
    </>
  );
}
