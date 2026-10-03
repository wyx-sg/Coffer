// src/lib/hooks/useAttentionIgnore.ts — ignore a "needs you" item on this machine.
//
// The daemon keeps the choice (PUT /attention/ignored/{key}), so the Overview,
// the sidebar's badges and the menu bar all read the same list: an ignored
// item leaves `items` and `counts_by_kind` and is listed under `ignored` (spec
// web-ui "Let the user ignore any item on Overview"). It refetches the
// attention list; a failure is a toast.
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

