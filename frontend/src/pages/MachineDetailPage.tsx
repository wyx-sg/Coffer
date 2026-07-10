// frontend/src/pages/MachineDetailPage.tsx — one machine's computed
// activation slice (spec 010-sync amendment, Task 18): which agents,
// mcp_servers, skills, and channels are active on that machine, derived
// locally from the synced registry plus each resource's scope (ADR-045).
// Intent only — no local FS/process checks; that distinction (actuals like
// quarantine/install state, available only when viewing the local machine's
// own slice) is out of scope for this task and surfaces as a hint instead.
// Layout mirrors SkillDetailPage.tsx: a back link, a title, then one Card per
// axis with a simple name + active/inactive Badge row.
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useMachineSlice, type SliceEntry } from "@/lib/hooks/useMachines";

/**
 * One row in a section: the resource's name (linking to its own detail page)
 * plus an active/inactive Badge. `entry.agents` is present only on the
 * dual-axis kinds (mcp_servers, skills) — it narrows by which bound agents
 * the resource is active for, shown as small text under the name.
 */
function SliceRow({ entry, href }: { entry: SliceEntry; href: string }) {
  const { t } = useTranslation();
  return (
    <Link
      to={href}
      className="flex items-center justify-between gap-3 rounded-md px-2 py-2 -mx-2 hover:bg-accent/50"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{entry.name}</p>
        {entry.agents && entry.agents.length > 0 ? (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{entry.agents.join(", ")}</p>
        ) : null}
      </div>
      <Badge variant={entry.active ? "default" : "secondary"}>
        {entry.active ? t("machines.slice.active") : t("machines.slice.inactive")}
      </Badge>
    </Link>
  );
}

function SliceSection({
  title,
  entries,
  hrefFor,
}: {
  title: string;
  entries: SliceEntry[];
  hrefFor: (name: string) => string;
}) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-serif text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("machines.slice.empty")}</p>
        ) : (
          <div className="divide-y divide-border">
            {entries.map((entry) => (
              <SliceRow key={entry.name} entry={entry} href={hrefFor(entry.name)} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function MachineDetailPage() {
  const { t } = useTranslation();
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: slice, isPending, error } = useMachineSlice(id);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  if (error || !slice) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">{t("machines.loadFailed")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {error ? translateApiError(t, error) : t("machines.loadFailed")}
          </p>
          <Button variant="link" onClick={() => navigate("/machines")} className="-ml-2">
            <ArrowLeft className="mr-1 size-4" />
            {t("machines.slice.back")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { machine } = slice;

  return (
    <div className="space-y-6">
      <div className="-ml-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/machines")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" /> {t("machines.slice.back")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-serif text-3xl tracking-tight">{machine.display_name}</h1>
        {machine.is_local && <Badge variant="secondary">{t("machines.thisMachine")}</Badge>}
      </div>

      {!machine.is_local ? (
        <p className="text-sm text-muted-foreground">{t("machines.slice.intentOnly")}</p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <SliceSection
          title={t("machines.slice.agents")}
          entries={slice.agents}
          hrefFor={(name) => `/agents/${encodeURIComponent(name)}`}
        />
        <SliceSection
          title={t("machines.slice.mcpServers")}
          entries={slice.mcp_servers}
          hrefFor={(name) => `/mcp-servers/mcp_server/${encodeURIComponent(name)}`}
        />
        <SliceSection
          title={t("machines.slice.skills")}
          entries={slice.skills}
          hrefFor={(name) => `/skills/${encodeURIComponent(name)}`}
        />
        <SliceSection
          title={t("machines.slice.channels")}
          entries={slice.channels}
          hrefFor={(name) => `/channels/${encodeURIComponent(name)}`}
        />
      </div>
    </div>
  );
}
