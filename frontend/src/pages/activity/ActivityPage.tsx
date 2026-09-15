import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ScrollText } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InvocationsTable } from "@/components/mcp/InvocationsTable";
import { ChangesTab } from "./ChangesTab";
import { DaemonTab } from "./DaemonTab";

type ActivityTab = "changes" | "mcp" | "daemon";

/**
 * Activity — the three records Coffer keeps: vault changes, the MCP calls it
 * proxied, and the daemon's own log. One tab each, because one merged table
 * could only carry the columns all three share: an invocation's duration and
 * status, and a log record's level, had nowhere to go, and a single "Detail"
 * header meant three different things. Each tab renders the record's own
 * table, with its own filters and its own loading / empty / error states —
 * so a route an older daemon does not serve fails inside its own tab instead
 * of blanking the two that work.
 *
 * Only the tab in front queries: Radix unmounts the others, and each tab is
 * handed `enabled` besides, so nothing is fetched and thrown away. There is
 * no refresh control — a record of what already happened is not a live
 * console. React Query refetches when the query key changes (switching tab,
 * changing a filter) and when a stale query remounts or the window regains
 * focus, which is every occasion this page has to be out of date.
 */
export function ActivityPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<ActivityTab>("changes");

  return (
    <div className="space-y-6">
      <PageHeader icon={ScrollText} title={t("activity.title")} subtitle={t("activity.subtitle")} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as ActivityTab)}>
        <TabsList>
          <TabsTrigger value="changes">{t("activity.tabs.changes")}</TabsTrigger>
          <TabsTrigger value="mcp">{t("activity.tabs.mcp")}</TabsTrigger>
          <TabsTrigger value="daemon">{t("activity.tabs.daemon")}</TabsTrigger>
        </TabsList>

        <TabsContent value="changes" className="pt-6">
          <ChangesTab enabled={tab === "changes"} />
        </TabsContent>
        <TabsContent value="mcp" className="pt-6">
          {/* The same table the MCP server detail page renders, with no server
              name: every server's calls, with a leading server column. */}
          <InvocationsTable enabled={tab === "mcp"} />
        </TabsContent>
        <TabsContent value="daemon" className="pt-6">
          <DaemonTab enabled={tab === "daemon"} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
