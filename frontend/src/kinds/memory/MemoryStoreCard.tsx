// frontend/src/kinds/memory/MemoryStoreCard.tsx
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import type { components } from "@/lib/api/types";
import { useEnableResource, useDisableResource } from "@/lib/hooks/useResourceMutations";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
}

function llmProvider(resource: ResourceOut): string {
  const cfg = resource.config as Record<string, unknown> | undefined;
  const p = cfg?.llm_provider;
  return typeof p === "string" ? p : "none";
}

export function MemoryStoreCard({ resource }: Props) {
  const enable = useEnableResource();
  const disable = useDisableResource();

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
          <Link
            to={`/resources/memory/${resource.name}`}
            className="text-base font-semibold hover:underline"
          >
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
          <Badge variant="secondary">LLM: {llmProvider(resource)}</Badge>
        </div>
        {resource.description ? (
          <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{resource.description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
