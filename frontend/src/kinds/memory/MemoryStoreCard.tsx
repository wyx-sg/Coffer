// frontend/src/kinds/memory/MemoryStoreCard.tsx
// Memory stores are auto-provisioned (global + per-project) and have no
// enable/disable knob beyond the resource one. The card shows the store's
// scope badge (no llm_provider anymore) and links to the store detail page.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import type { components } from "@/lib/api/types";
import { deriveScope } from "@/kinds/memory/api";
import { useEnableResource, useDisableResource } from "@/lib/hooks/useResourceMutations";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
}

export function MemoryStoreCard({ resource }: Props) {
  const { t } = useTranslation();
  const enable = useEnableResource();
  const disable = useDisableResource();

  // Derive scope from project_id vs the WORKSPACE_GLOBAL sentinel (or an
  // explicit scope) instead of defaulting to "global"; show an explicit
  // "unknown" label when neither signal is present.
  const scope = deriveScope(resource as Parameters<typeof deriveScope>[0]);
  const scopeLabel = scope ? t(`memory.scope.${scope}`) : t("memory.scope.unknown");

  const handleToggle = (checked: boolean) => {
    if (checked) {
      enable.mutate({ kind: resource.kind, name: resource.name });
    } else {
      disable.mutate({ kind: resource.kind, name: resource.name });
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <Link to={`/memory/${resource.name}`} className="text-base font-semibold hover:underline">
            {resource.name}
          </Link>
          <Switch
            checked={resource.enabled}
            onCheckedChange={handleToggle}
            disabled={enable.isPending || disable.isPending}
            aria-label={resource.enabled ? "disable" : "enable"}
          />
        </div>
        <CardTitle className="sr-only">{resource.name}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="secondary">{scopeLabel}</Badge>
        </div>
        {resource.description ? (
          <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{resource.description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
