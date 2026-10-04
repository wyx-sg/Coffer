// src/components/settings/storage/CacheBlock.tsx — Settings › Data's Rebuildable cache block and its confirmed Clear (canvas 1.4.11).
//
// Spec web-ui "Group the Data tab by what kind of data it is": the memory tree
// and the transcript summary cache, which Coffer rebuilds on its own. One Clear
// behind a confirmation that says what comes back and what does not; the
// dialog closes only when the clear succeeded, and keeps its error otherwise.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { useClearCache } from "@/lib/hooks/useStorage";
import { formatBytes } from "@/lib/utils";
import { DataBlock } from "./DataBlock";

interface Props {
  bytes: number | null;
}

export function CacheBlock({ bytes }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const clear = useClearCache();
  const [open, setOpen] = useState(false);
  const size = bytes === null ? null : formatBytes(bytes);

  return (
    <>
      <DataBlock
        title={t("settings.data.cache.title")}
        size={size}
        description={t("settings.data.cache.description")}
        testId="settings-data-cache"
        action={
          <Button
            size="sm"
            variant="outline"
            onClick={() => setOpen(true)}
            disabled={bytes === null}
          >
            {t("settings.data.cache.clear")}
          </Button>
        }
      />
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) clear.reset();
        }}
        title={t("settings.data.cache.confirmTitle")}
        description={t("settings.data.cache.confirmBody", { size: size ?? "" })}
        confirmLabel={
          clear.isPending ? t("settings.data.cache.clearing") : t("settings.data.cache.confirm")
        }
        pending={clear.isPending}
        error={clear.error}
        onConfirm={() =>
          clear.mutate(undefined, {
            onSuccess: (freed) => {
              setOpen(false);
              toast.success(t("settings.data.cache.cleared", { size: formatBytes(freed) }));
            },
          })
        }
      />
    </>
  );
}
