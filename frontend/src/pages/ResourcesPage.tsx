// frontend/src/pages/ResourcesPage.tsx
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listKindUIs } from "@/lib/components/kindRegistry";
import { ResourceListView } from "@/lib/components/ResourceListView";
import { Pagination } from "@/components/Pagination";
import { AddMcpServerDialog } from "@/kinds/mcp/AddMcpServerDialog";
import { WelcomePanel } from "./resources/WelcomePanel";
import { ResourcesToolbar } from "./resources/ResourcesToolbar";
import { useResources } from "@/lib/hooks/useResources";
import { translateApiError } from "@/lib/api/errors";

/**
 * The resources landing surface.
 *
 *   - empty: a welcome card explaining Coffer + the obvious next step.
 *   - non-empty: a search / status toolbar, a grid of kind-specific cards,
 *     and a client-side pager — so a large vault stays navigable.
 */
export function ResourcesPage() {
  const { t } = useTranslation();
  const kinds = listKindUIs();
  const [selectedKind, setSelectedKind] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const { data: resources, isPending, error } = useResources(selectedKind);
  const hasResources = (resources?.length ?? 0) > 0;

  // Memoised so a keystroke / card-status settling elsewhere doesn't re-run
  // the O(n) name+status filter on every render.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (resources ?? []).filter((r) => {
      if (q && !r.name.toLowerCase().includes(q)) return false;
      if (status === "enabled" && !r.enabled) return false;
      if (status === "disabled" && r.enabled) return false;
      return true;
    });
  }, [resources, search, status]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const pageItems = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div className="space-y-8">
      <PageHeader showAdd={hasResources} />

      {!hasResources && !isPending && !error ? <WelcomePanel /> : null}

      {hasResources && kinds.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          <Button
            variant={selectedKind === undefined ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setSelectedKind(undefined);
              setPage(1);
            }}
          >
            {t("resources.all")}
          </Button>
          {kinds.map((kind) => (
            <Button
              key={kind.name}
              variant={selectedKind === kind.name ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setSelectedKind(kind.name);
                setPage(1);
              }}
            >
              {kind.displayName}
            </Button>
          ))}
        </div>
      ) : null}

      {isPending ? (
        <Card className="paper-card">
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card className="paper-card border-destructive/40">
          <CardHeader>
            <CardTitle className="font-serif text-destructive">
              {t("resources.loadFailed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : hasResources ? (
        <div className="space-y-4">
          <ResourcesToolbar
            search={search}
            onSearchChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
            status={status}
            onStatusChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <ResourceListView resources={pageItems} emptyMessage={t("resources.noMatches")} />
          <Pagination
            page={safePage}
            pageCount={pageCount}
            total={filtered.length}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(s) => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function PageHeader({ showAdd }: { showAdd: boolean }) {
  const { t } = useTranslation();
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1 className="flex items-center gap-3 text-3xl tracking-tight">
          <Server className="size-7 text-primary" strokeWidth={1.5} aria-hidden />
          {t("resources.title")}
        </h1>
        <p className="max-w-prose text-sm text-muted-foreground">{t("resources.subtitle")}</p>
      </div>
      {showAdd ? <AddMcpServerDialog /> : null}
    </header>
  );
}
