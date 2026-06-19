import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { RegistryResultRow } from "./RegistryResultRow";
import { RegistryServerForm } from "./RegistryServerForm";
import type { ParsedServer } from "./jsonImport";
import type { components } from "@/lib/api/types";

type RegistryServer = components["schemas"]["RegistryServerOut"];

interface Props {
  /** Feeds the dialog's existing import pipeline. */
  onImport: (servers: ParsedServer[]) => void;
  importing: boolean;
}

async function searchRegistry(q: string): Promise<RegistryServer[]> {
  const client = getApiClient();
  const { data, error } = await client.GET("/mcp-registry/search", {
    params: { query: { q, limit: 30 } },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "registry search failed");
  return data?.servers ?? [];
}

/**
 * The "Search registry" tab: query the official MCP Registry, list the
 * results, and let an installable entry be configured and handed to the
 * dialog's existing import pipeline. A 502 (REGISTRY_UNAVAILABLE) shows a
 * graceful message that points the user at the Paste-JSON tab.
 */
export function RegistrySearchPanel({ onImport, importing }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RegistryServer | null>(null);

  const search = useMutation({
    mutationFn: searchRegistry,
    onSuccess: () => setSelected(null),
  });

  function handleSearch() {
    const q = query.trim();
    if (q === "") return;
    search.mutate(q);
  }

  if (selected) {
    return (
      <RegistryServerForm
        server={selected}
        importing={importing}
        onBack={() => setSelected(null)}
        onAdd={(parsed) => onImport([parsed])}
      />
    );
  }

  const unavailable =
    search.error instanceof ApiError && search.error.code === "REGISTRY_UNAVAILABLE";
  const results = search.data ?? [];

  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          handleSearch();
        }}
      >
        <Input
          aria-label={t("mcp.registry.search")}
          placeholder={t("mcp.registry.searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" disabled={search.isPending || query.trim() === ""}>
          <Search className="mr-1 size-4" />
          {search.isPending ? t("mcp.registry.searching") : t("mcp.registry.search")}
        </Button>
      </form>

      {unavailable ? (
        <p className="text-sm text-destructive" role="alert">
          {t("mcp.registry.unavailable")}
        </p>
      ) : search.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {search.error instanceof Error ? search.error.message : String(search.error)}
        </p>
      ) : null}

      {search.isSuccess && results.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("mcp.registry.noResults")}</p>
      ) : null}

      {results.length > 0 ? (
        <div className="space-y-2">
          {results.map((srv) => (
            <RegistryResultRow key={srv.name} server={srv} onUse={setSelected} />
          ))}
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">{t("mcp.registry.poweredBy")}</p>
    </div>
  );
}
