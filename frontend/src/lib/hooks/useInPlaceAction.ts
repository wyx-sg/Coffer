// src/lib/hooks/useInPlaceAction.ts — run a "Needs you" row's action where the row is.
//
// An action in lib/overview/attention `inPlaceVerb` calls the daemon's own
// route through the typed client (the item's `action.path` names that route;
// the call is made through the request function that owns it). The row is
// "in progress" from the click until the attention list has refetched after
// the call settled: an item that is gone leaves the list, one that is still
// there goes back to its normal button, and a failed call reverts at once
// with the error as a toast (spec web-ui "Show what needs the user and each
// area's health on Overview").
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { clisApi } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { mcpServersApi } from "@/lib/api/mcpServers";
import { attentionKey } from "@/lib/api/queryKeys";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { inPlaceVerb } from "@/lib/overview/attention";

async function call(item: AttentionItem): Promise<void> {
  if (item.kind === "mcp_server" && item.uid) await mcpServersApi.test(item.uid);
  else if (item.kind === "cli" && item.uid) await clisApi.check(item.uid);
}

/** The keys of the items whose action is running, and the function that runs one. */
export function useInPlaceActions() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  const [running, setRunning] = useState<ReadonlySet<string>>(new Set());
  const set = (key: string, on: boolean) =>
    setRunning((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  const run = useCallback(
    async (item: AttentionItem) => {
      if (!inPlaceVerb(item)) return;
      set(item.key, true);
      try {
        await call(item);
        // Resolves once the list has been read again.
        await qc.invalidateQueries({ queryKey: attentionKey });
      } catch (e) {
        toast.error(translateApiError(t, e));
      } finally {
        set(item.key, false);
      }
    },
    [qc, t, toast],
  );
  return { running, run };
}
