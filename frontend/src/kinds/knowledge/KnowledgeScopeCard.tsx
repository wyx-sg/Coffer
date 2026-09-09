// frontend/src/kinds/knowledge/KnowledgeScopeCard.tsx
// One knowledge scope as a card, for the kind-agnostic resource grid. The
// global and per-project scopes auto-provision; a named collection is created
// deliberately. The card shows the scope badge and links to the detail page.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import type { components } from "@/lib/api/types";
import { deriveScope } from "@/kinds/knowledge/api";
import { useEnableResource, useDisableResource } from "@/lib/hooks/useResourceMutations";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
}

export function KnowledgeScopeCard({ resource }: Props) {
  const { t } = useTranslation();
  const enable = useEnableResource();
  const disable = useDisableResource();

  // The scope kind is encoded in the resource NAME (`global`, `project-<ULID>`,
  // anything else = a named collection), so a generic resource row still
  // labels correctly; an explicit `scope` on the row wins when present.
  const scope = deriveScope(resource as Parameters<typeof deriveScope>[0]);
  const scopeLabel = scope ? t(`knowledge.scope.${scope}`) : t("knowledge.scope.unknown");

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
            to={`/knowledge/${resource.name}`}
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
          <Badge variant="secondary">{scopeLabel}</Badge>
        </div>
        {resource.description ? (
          <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{resource.description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
