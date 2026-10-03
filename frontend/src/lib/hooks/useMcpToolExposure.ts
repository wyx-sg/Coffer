// src/lib/hooks/useMcpToolExposure.ts — set how one or many of a server's tools are exposed to agents (spec mcp-gateway "Forward tools, resources and prompts").
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { mcpTieringsKey } from "@/lib/api/queryKeys";
import { mcpServersApi, type ToolExposureMode } from "@/lib/api/mcpServers";

interface Input {
  serverUid: string;
  tools: readonly string[];
  mode: ToolExposureMode;
}

/** The split is machine-wide (one server's pin moves another's slot), so every server's tiering refreshes. */
export function useSetToolExposure() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ serverUid, tools, mode }: Input) =>
      mcpServersApi.setToolExposure(serverUid, tools, mode),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: mcpTieringsKey });
      if (vars.tools.length > 1)
        toast.success(t("mcp.exposure.bulkDone", { count: vars.tools.length }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
