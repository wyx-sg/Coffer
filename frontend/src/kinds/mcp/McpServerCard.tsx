// frontend/src/kinds/mcp/McpServerCard.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/api/types";
import {
  useEnableResource,
  useDisableResource,
  useDeleteResource,
} from "@/lib/hooks/useResourceMutations";
import { useMcpServerStatus } from "@/lib/hooks/useMcpInvocations";
import { HealthBadge } from "./HealthBadge";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
}

function transportObj(resource: ResourceOut): Record<string, unknown> | null {
  const transport = (resource.config as Record<string, unknown> | undefined)?.transport;
  return transport && typeof transport === "object" ? (transport as Record<string, unknown>) : null;
}

function transportType(resource: ResourceOut): string {
  const t = transportObj(resource)?.type;
  return typeof t === "string" ? t : "unknown";
}

export function McpServerCard({ resource }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const enable = useEnableResource();
  const disable = useDisableResource();
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const detailPath = `/resources/mcp_server/${resource.name}`;
  const transport = transportType(resource);
  // Status from the most recent invocation; null = never invoked.
  const { data: status } = useMcpServerStatus(resource.name);

  const handleToggle = (checked: boolean) => {
    if (checked) {
      enable.mutate({ kind: resource.kind, name: resource.name });
    } else {
      disable.mutate({ kind: resource.kind, name: resource.name });
    }
  };

  const handleDelete = () => {
    del.mutate(
      { kind: resource.kind, name: resource.name },
      { onSettled: () => setDeleteOpen(false) },
    );
  };

  return (
    <>
      {/* The whole card is the link — keyboard-focusable, Enter opens it. */}
      <Card
        role="link"
        tabIndex={0}
        onClick={() => navigate(detailPath)}
        onKeyDown={(e) => {
          if (e.key === "Enter") navigate(detailPath);
        }}
        className={cn(
          "cursor-pointer transition-colors hover:border-primary/40",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base font-semibold">{resource.name}</CardTitle>
            {/* Controls must not trigger the card's navigation. */}
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground hover:text-destructive"
                onClick={() => setDeleteOpen(true)}
                aria-label={t("mcp.server.deleteServer")}
              >
                <Trash2 className="size-4" />
              </Button>
              <Switch
                checked={resource.enabled}
                onCheckedChange={handleToggle}
                disabled={enable.isPending || disable.isPending}
                aria-label={resource.enabled ? t("common.enabled") : t("common.disabled")}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          {resource.description ? (
            <p className="line-clamp-2 text-xs text-muted-foreground">{resource.description}</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {status ? <HealthBadge state={status} /> : null}
            <Badge variant="secondary">{transport}</Badge>
            {resource.enabled ? (
              <Badge variant="default">{t("common.enabled").toLowerCase()}</Badge>
            ) : (
              <Badge variant="outline">{t("common.disabled").toLowerCase()}</Badge>
            )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("mcp.server.deleteConfirmTitle", { name: resource.name })}</DialogTitle>
            <DialogDescription>{t("mcp.server.deleteConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={del.isPending}>
              {del.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
