// src/lib/hooks/useAttentionIgnore.ts — ignore a "needs you" item on this machine.
//
// The daemon keeps the choice (PUT /attention/ignored/{key}), so the Overview
// and the menu bar both read the same list: an ignored
// item leaves `items` and `counts_by_kind` and is listed under `ignored` (spec
// web-ui "Let the user ignore any item on Overview"). It refetches the
// attention list; a failure is a toast. `useUnignoreAttention` puts one back
// (DELETE), from the item's own page.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { attentionApi } from "@/lib/api/attention";
import { translateApiError } from "@/lib/api/errors";
import { attentionKey } from "@/lib/api/queryKeys";

/** Ignore one item by its `key`. */
export function useIgnoreAttention() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (key: string) => attentionApi.ignore(key),
    onSuccess: () => void qc.invalidateQueries({ queryKey: attentionKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}


/** Stop ignoring one item by its `key`: it is back on Overview. */
export function useUnignoreAttention() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (key: string) => attentionApi.unignore(key),
    onSuccess: () => {
      toast.success(t("overview.needsYou.backOnOverview"));
      void qc.invalidateQueries({ queryKey: attentionKey });
    },
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}
