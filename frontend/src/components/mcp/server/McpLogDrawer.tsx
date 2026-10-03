// src/components/mcp/server/McpLogDrawer.tsx — "<name> · Calls and server log", a side drawer over the MCP servers page (design 4.1.09, 4.1.10).
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import { cn } from "@/lib/utils";
import { McpCallsLog } from "./McpCallsLog";
import { McpServerLogView } from "./McpServerLogView";
import { transportOf } from "@/lib/mcp/serverState";

export type LogTab = "calls" | "log";

interface Props {
  resource: ResourceOut;
  agents: readonly AgentOut[];
  summary: InvocationSummary | undefined;
  tab: LogTab | null;
  onTabChange: (tab: LogTab) => void;
  onClose: () => void;
}

export function McpLogDrawer({ resource, agents, summary, tab, onTabChange, onClose }: Props) {
  const { t } = useTranslation();
  const isHttp = transportOf(resource.config).type === "http";
  return (
    <DialogPrimitive.Root
      open={tab !== null}
      onOpenChange={(open) => (open ? undefined : onClose())}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-dialog bg-scrim" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          data-testid="mcp-log-drawer"
          className={cn(
            "fixed inset-y-0 right-0 z-dialog flex w-[min(640px,100vw)] flex-col gap-4 overflow-hidden border-l border-border bg-surface-raised p-5 text-sm text-text shadow-overlay outline-none",
          )}
        >
          <div className="flex items-start gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <DialogPrimitive.Title className="text-md font-bold">
                {t("mcp.page.log.title", { name: resource.name })}
              </DialogPrimitive.Title>
              <p className="text-xs text-text-muted">
                {tab !== "log" && summary
                  ? t("mcp.page.log.subtitle", { calls: summary.calls, errors: summary.errors })
                  : isHttp
                    ? t("mcp.page.log.subtitleHttp")
                    : t("mcp.page.log.subtitleStdio")}
              </p>
            </div>
            <DialogPrimitive.Close
              aria-label={t("common.close")}
              className="inline-flex size-7 items-center justify-center rounded-item text-text-muted hover:bg-surface-hover hover:text-text"
            >
              <X className="size-4" aria-hidden />
            </DialogPrimitive.Close>
          </div>
          <Tabs
            value={tab ?? "calls"}
            onValueChange={(v) => onTabChange(v as LogTab)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <TabsList>
              <TabsTrigger value="calls">{t("mcp.page.log.callsTab")}</TabsTrigger>
              <TabsTrigger value="log">{t("mcp.page.log.logTab")}</TabsTrigger>
            </TabsList>
            <TabsContent
              value="calls"
              className="flex min-h-0 flex-1 flex-col pt-4 data-[state=inactive]:hidden"
            >
              <McpCallsLog serverUid={resource.uid} agents={agents} />
            </TabsContent>
            <TabsContent
              value="log"
              className="flex min-h-0 flex-1 flex-col pt-4 data-[state=inactive]:hidden"
            >
              <McpServerLogView serverUid={resource.uid} isHttp={isHttp} />
            </TabsContent>
          </Tabs>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
