// src/components/agents/hooks/OwnHooksSection.tsx — the agent's own hooks, one table (boards 2.1.34, 2.1.64).
//
// Event · Command · Matcher · File, one bordered container, the whole row
// opening the read-only details dialog. Above it, a search (command or file) and
// the Event filter, with "Showing N of M" at the right once either narrows the
// list. Coffer's own hook is not in this table: it has the section above.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { TabEmpty } from "../tabs/TabEmpty";
import { HookDetailsDialog } from "@/components/agents/hooks/HookDetailsDialog";
import { HookEventFilter } from "@/components/agents/hooks/HookEventFilter";
import { Section } from "@/components/Section";
import { SearchInput } from "@/components/SearchInput";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { fileName, filterEvents, hookKey, hookTotals } from "@/lib/agents/hookRows";
import type { NativeHook } from "@/lib/api/agents";

interface Props {
  hooks: readonly NativeHook[];
  agentType: string;
  /** The Config files key that holds a file path, when one does. */
  fileKeyOf: (path: string) => string | null;
}

/** A plugin's hook reads "<plugin> · hooks.json"; a user file reads as its path. */
function fileLabel(h: NativeHook): string {
  return h.plugin ? `${h.plugin.split("@")[0]} · ${fileName(h.path)}` : abbreviateHomePath(h.path);
}

export function OwnHooksSection({ hooks, agentType, fileKeyOf }: Props) {
  const { t } = useTranslation();
  const agent = agentTypeLabel(agentType);
  const [query, setQuery] = useState("");
  const [event, setEvent] = useState<string | null>(null);
  const [open, setOpen] = useState<NativeHook | null>(null);

  const events = useMemo(() => filterEvents(hooks), [hooks]);
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const h of hooks) out[h.event] = (out[h.event] ?? 0) + 1;
    return out;
  }, [hooks]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return hooks.filter(
      (h) => (event === null || h.event === event) && (!q || h.command.toLowerCase().includes(q)),
    );
  }, [hooks, query, event]);
  const totals = hookTotals(hooks);
  const filtered = event !== null || query.trim() !== "";

  return (
    <Section
      as="h2"
      title={t("agents.hooks.own.title", { agent })}
      help={t("agents.hooks.own.help")}
      gap="tight"
      testId="own-hooks-section"
    >
      {hooks.length === 0 ? (
        <TabEmpty
          title={t("agents.hooks.own.emptyTitle", { agent })}
          description={t("agents.hooks.own.emptyBody", { agent })}
        />
      ) : (
        <>
          <p className="mb-1 text-xs text-text-muted">
            {t("agents.hooks.own.summary", {
              hooks: t("agents.hooks.own.hooks", { count: totals.hooks }),
              files: t("agents.hooks.own.files", { count: totals.files }),
              agent,
            })}
          </p>
          <div className="flex items-center gap-2 pb-1">
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder={t("agents.hooks.own.search")}
              ariaLabel={t("agents.hooks.own.search")}
              className="w-64"
            />
            <HookEventFilter
              value={event}
              onChange={setEvent}
              events={events}
              counts={counts}
              total={hooks.length}
            />
            {filtered ? (
              <span className="ml-auto text-xs text-text-muted">
                {t("agents.hooks.own.showing", { shown: shown.length, total: hooks.length })}
              </span>
            ) : null}
          </div>
          <div className="overflow-hidden rounded-lg border border-border bg-surface-raised">
            <table className="w-full table-fixed border-collapse text-left">
              <thead>
                <tr className="border-b border-border-subtle text-xs font-medium text-text-muted">
                  <th className="w-[19%] px-4 py-2.5 font-medium">
                    {t("agents.hooks.own.colEvent")}
                  </th>
                  <th className="px-2 py-2.5 font-medium">{t("agents.hooks.own.colCommand")}</th>
                  <th className="w-[13%] px-2 py-2.5 font-medium">
                    {t("agents.hooks.own.colMatcher")}
                  </th>
                  <th className="w-[26%] px-2 py-2.5 font-medium">
                    {t("agents.hooks.own.colFile")}
                  </th>
                  <th className="w-10" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {shown.map((h) => (
                  <tr
                    key={hookKey(h)}
                    tabIndex={0}
                    onClick={() => setOpen(h)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setOpen(h);
                      }
                    }}
                    className="cursor-pointer border-b border-border-subtle last:border-b-0 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
                  >
                    <td className="px-4 py-3 align-middle font-mono text-xs font-medium text-text">
                      {h.event}
                    </td>
                    <td className="px-2 py-3 align-middle">
                      <TruncatedText mono text={h.command} className="text-xs text-text" />
                    </td>
                    <td className="px-2 py-3 align-middle text-xs">
                      {h.matcher ? (
                        <TruncatedText mono text={h.matcher} className="text-xs text-text-muted" />
                      ) : (
                        <span className="text-sm text-text-subtle">
                          {t("agents.hooks.own.matcherAny")}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-3 align-middle">
                      <TruncatedText mono text={fileLabel(h)} className="text-xs text-text-muted" />
                    </td>
                    <td className="pr-3 align-middle">
                      <ChevronRight className="size-4 text-text-subtle" aria-hidden />
                    </td>
                  </tr>
                ))}
                {shown.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-sm text-text-muted">
                      {t("agents.hooks.own.noMatches")}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </>
      )}
      <HookDetailsDialog
        hook={open}
        agentType={agentType}
        fileKey={open ? fileKeyOf(open.path) : null}
        onClose={() => setOpen(null)}
      />
    </Section>
  );
}
