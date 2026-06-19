import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/types";

type RegistryServer = components["schemas"]["RegistryServerOut"];

interface Props {
  server: RegistryServer;
  onUse: (server: RegistryServer) => void;
}

/**
 * One row in the registry search results. Installable servers (draft != null)
 * get a "Use" action; non-installable ones show a muted note plus a homepage
 * link when present.
 */
export function RegistryResultRow({ server, onUse }: Props) {
  const { t } = useTranslation();
  const installable = server.draft != null;
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-medium break-all">{server.title || server.name}</div>
          <p className="mt-0.5 text-xs text-muted-foreground">{server.description}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {server.registry_type ? (
              <Badge variant="secondary">{server.registry_type}</Badge>
            ) : null}
            <Badge variant="outline">{server.transport_type}</Badge>
          </div>
        </div>
        {installable ? (
          <Button size="sm" className="shrink-0" onClick={() => onUse(server)}>
            {t("mcp.registry.use")}
          </Button>
        ) : null}
      </div>
      {!installable ? (
        <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <span>{t("mcp.registry.notInstallable")}</span>
          {server.homepage ? (
            <a
              href={server.homepage}
              target="_blank"
              rel="noreferrer"
              className="underline hover:text-foreground"
            >
              {t("mcp.registry.homepage")}
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
