// src/components/agents/detail/useRotateProxyToken.ts — "Rotate proxy token" for the agent header's ⋯ menu.
//
// Only an agent that currently routes through Coffer's proxy (it runs on a
// provider, not its built-in login, and the proxy has a route for it) has a
// proxy token to rotate. Rotating is immediate; the agent fetches the new token
// on its next request.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { proxyApi, proxyTokenHintKey } from "@/lib/api/proxy";
import { useProxyRoute } from "@/lib/hooks/useProviderFallback";

/** The menu action, or null while the agent does not route through Coffer's proxy. */
export function useRotateProxyAction(agent: AgentOut | undefined): MenuAction | null {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const uid = agent?.uid ?? "";
  const onProvider = !!agent?.connection_uid;
  const route = useProxyRoute(uid, agent?.model ?? null, onProvider);
  const rotate = useMutation({
    mutationFn: () => proxyApi.rotateToken(uid),
    onSuccess: () => {
      toast.success(t("agents.detail.rotateToken.done"));
      return qc.invalidateQueries({ queryKey: proxyTokenHintKey(uid) });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
  if (!onProvider || !route.data?.primary) return null;
  return {
    key: "rotate-token",
    label: t("agents.detail.rotateToken.label"),
    onSelect: () => rotate.mutate(),
    disabled: rotate.isPending,
  };
}
