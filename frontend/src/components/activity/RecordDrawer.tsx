// src/components/activity/RecordDrawer.tsx — one Activity record opened in the shared right-hand Drawer (Foundations 0.4.02).
//
// The title names the record and a mono line gives its kind and time; the body
// answers first, then gives context, then the next step (design 6.2.01,
// 6.2.07): a failed call leads with its conclusion card, a change with the
// facts (Who / What), then what it changed (the config before and after, as a
// diff); a daemon record with its message and traceback. Below come the
// records written around the same time and the raw JSON, open. The footer
// holds the next step — "Open X" secondary, "Copy details" ghost — and the
// drawer steps to the previous or next record without closing. An MCP call
// shows its metadata only: Coffer never stores a call's arguments or results.
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { CodeView } from "@/components/preview/CodeView";
import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { describeActivity } from "@/lib/activity/activityText";
import { callServerLabel, recordLogger, type ActivityRecord } from "@/lib/activity/records";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import {
  UID_ADDRESSED_KINDS,
  changeLink,
  nearby,
  offsetLabel,
  whenLabel,
} from "@/lib/activity/recordText";
import { useResources } from "@/lib/hooks/useResources";
import { useServerFailures } from "@/lib/hooks/useServerFailures";
import { EventCell, SourceIcon, type AgentLook } from "./activityCells";
import { CallBody, ChangeBody, DaemonBody } from "./recordBodies";
import { Section } from "@/components/Section";

function titleOf(t: TFunction, record: ActivityRecord): string {
  if (record.source === "call")
    return `${callServerLabel(record.call)}.${record.call.capability_key}`;
  if (record.source === "change") return describeActivity(t, record.entry);
  return recordLogger(record) || t("activity.drawer.kinds.daemon");
}

/** The raw JSON, open by default and foldable. */
function RawLogFold({ record }: { record: unknown }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex w-fit items-center gap-1.5 text-sm font-semibold text-text"
      >
        <Chevron className="size-3.5 text-text-subtle" aria-hidden />
        {t("common.rawLog")}
      </button>
      {open ? (
        <CodeView
          value={JSON.stringify(record, null, 2)}
          language="json"
          maxHeight="24rem"
          ariaLabel={t("common.rawLog")}
          className="bg-surface-sunken"
        />
      ) : null}
    </div>
  );
}

interface Props {
  record: ActivityRecord;
  /** The rows on screen, for previous / next and "around the same time". */
  rows: readonly ActivityRecord[];
  agents: ReadonlyMap<string, AgentLook>;
  /** MCP server uid → its transport. */
  transports: ReadonlyMap<string, "stdio" | "http" | "unknown">;
  onSelect: (key: string) => void;
  onClose: () => void;
}

export function RecordDrawer({ record, rows, agents, transports, onSelect, onClose }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const index = rows.findIndex((r) => r.key === record.key);
  const previous = index > 0 ? rows[index - 1] : undefined;
  const next = index >= 0 && index < rows.length - 1 ? rows[index + 1] : undefined;
  const around = nearby(record, rows);
  const call = record.source === "call" ? record.call : null;
  const failures = useServerFailures(call);

  // The hand-off prompt is the drawer's to use, not part of the record.
  const raw =
    record.source === "change"
      ? record.entry
      : record.source === "call"
        ? { ...record.call, handoff: undefined }
        : { ...record.log.record };

  const copy = (text: string) => {
    void navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(t("activity.drawer.copied")))
      .catch(() => toast.error(t("activity.drawer.copyFailed")));
  };

  const pageOpen = useKindPageOpen();
  // A change to a uid-addressed kind looks its resource up by name to open its detail page.
  const changeKind = record.source === "change" ? (record.entry.resource_kind ?? "") : "";
  const needsUid = UID_ADDRESSED_KINDS.includes(changeKind);
  const { data: sameKind } = useResources(needsUid ? changeKind : "-", needsUid);
  const changedUid =
    record.source === "change"
      ? sameKind?.find((r) => r.name === record.entry.resource_name)?.uid
      : undefined;
  const link =
    record.source === "change"
      ? pageOpen(changeKind)
        ? changeLink(record.entry, changedUid)
        : null
      : call?.resource_name
        ? { to: `/mcp-servers/${encodeURIComponent(call.resource_name)}`, name: call.resource_name }
        : null;

  const copyButton = (
    <Button key="copy" variant="ghost" onClick={() => copy(JSON.stringify(raw, null, 2))}>
      {t(record.source === "daemon" ? "activity.drawer.copyRecord" : "activity.drawer.copyDetails")}
    </Button>
  );
  const openButton = link ? (
    <Button key="open" asChild variant="outline">
      <Link to={link.to}>{t("activity.drawer.open", { name: link.name })}</Link>
    </Button>
  ) : null;
  const footer: ReactNode[] = [];
  if (record.source === "daemon") {
    if (record.log.handoff) {
      footer.push(<AgentHandoff key="ask" prompt={record.log.handoff.prompt} />);
    }
    footer.push(copyButton);
  } else if (call) {
    // The call's next step is its server; a call with no server page to open copies itself.
    footer.push(openButton ?? copyButton);
  } else {
    footer.push(copyButton, openButton);
  }

  const kind = t(`activity.drawer.kinds.${record.source}`);
  const when = record.at ? whenLabel(t, record.at, record.source !== "change", i18n.language) : "";

  return (
    <Drawer
      open
      onOpenChange={(open) => !open && onClose()}
      title={titleOf(t, record)}
      subtitle={when ? `${kind} · ${when}` : kind}
      onPrevious={() => previous && onSelect(previous.key)}
      onNext={() => next && onSelect(next.key)}
      hasPrevious={!!previous}
      hasNext={!!next}
      footer={footer}
      bodyClassName="flex flex-col gap-5"
    >
      {record.source === "change" ? <ChangeBody t={t} entry={record.entry} /> : null}
      {call ? (
        <CallBody
          t={t}
          call={call}
          agents={agents}
          transport={transports.get(call.resource_uid)}
          failures={failures}
        />
      ) : null}
      {record.source === "daemon" ? <DaemonBody t={t} log={record.log} record={record} /> : null}

      {around.length ? (
        <Section title={t("activity.drawer.around")} gap="tight">
          <div className="flex flex-col overflow-hidden rounded-[10px] border border-border">
            {around.map((r, i) => (
              <button
                key={r.key}
                type="button"
                onClick={() => onSelect(r.key)}
                className={
                  "flex min-h-[34px] items-center gap-2.5 px-3 text-left hover:bg-surface-hover" +
                  (i > 0 ? " border-t border-border-subtle" : "")
                }
              >
                <SourceIcon record={r} />
                <span className="min-w-0 flex-1">
                  <EventCell t={t} record={r} />
                </span>
                <span className="shrink-0 font-mono text-xs text-text-muted">
                  {offsetLabel(t, record, r)}
                </span>
              </button>
            ))}
          </div>
        </Section>
      ) : null}

      <RawLogFold record={raw} />
    </Drawer>
  );
}
