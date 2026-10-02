// src/lib/hooks/useAttentionIgnore.ts — ignore an informational "needs you" item on this machine, or stop ignoring it.
//
// The daemon keeps the choice (PUT / DELETE /attention/ignored/{key}), so the
// Overview, the sidebar's badges and the menu bar all read the same list: an
// ignored item leaves `items` and `counts_by_kind` and is listed under
// `ignored` (spec web-ui "Let the user ignore an unconnected agent on
// Overview"). Both refetch the attention list; a failure is a toast.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { attentionApi } from "@/lib/api/attention";
import { translateApiError } from "@/lib/api/errors";
import { attentionKey } from "@/lib/api/queryKeys";

function useAttentionKeyMutation(method: "PUT" | "DELETE") {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (key: string) =>
      method === "PUT" ? attentionApi.ignore(key) : attentionApi.unignore(key),
    onSuccess: () => void qc.invalidateQueries({ queryKey: attentionKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Ignore one item by its `key`. */
export function useIgnoreAttention() {
  return useAttentionKeyMutation("PUT");
}

/** Stop ignoring one item by its `key`. */
export function useUnignoreAttention() {
  return useAttentionKeyMutation("DELETE");
}
