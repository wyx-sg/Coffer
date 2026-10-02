// src/components/activity/DaemonLogParts.tsx — the Daemon log tab's own pieces: the file line above the rows and a record opened in place.
//
// Design 6.1.09: the tab names the file it reads ("~/.coffer/logs/daemon.log ·
// newest first · following"), and a row opens under its own line with its
// traceback, a way to the MCP call it is about, and Copy record. "Open log
// file" hands the file to the editor through the daemon (`POST /fs/open`).
import { useTranslation } from "react-i18next";
import { Copy, FileText, Server } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { daemonContinuation, describeDaemonRecord } from "@/lib/activity/activityText";
import type { ActivityRecord } from "@/lib/activity/records";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import { useFsActions } from "@/lib/fsActions";

export function OpenLogFile({ path }: { path: string | undefined }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={!path}
      onClick={() => {
        if (path) fs.open(path).catch((e: unknown) => toast.error(translateApiError(t, e)));
      }}
    >
      <FileText />
      {t("activity.daemonLog.open")}
    </Button>
  );
}

export function DaemonLogLine({ path, following }: { path: string; following: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 px-3 pb-1.5 text-xs text-text-muted">
      <span title={path} className="whitespace-nowrap font-mono">
        {abbreviateHomePath(path)}
      </span>
      <span>
        {following ? t("activity.daemonLog.following") : t("activity.daemonLog.newestFirst")}
      </span>
    </div>
  );
}

/**
 * The MCP call a daemon record is about, as the text the MCP calls tab's box
 * finds it by (`server.tool`): from the record's own fields, or from the
 * `server=… tool=…` its message spells out.
 */
function callSearchOf(r: ActivityRecord): string | null {
  if (r.source !== "daemon") return null;
  const fields = r.log.record ?? {};
  const message = r.log.event ?? "";
  const pick = (key: string): string | null => {
    const value = fields[key];
    if (typeof value === "string" && value) return value;
    const match = new RegExp(`\\b${key}=(\\S+)`).exec(message);
    return match ? match[1] : null;
  };
  const server = pick("server");
  const tool = pick("tool");
  return server && tool ? `${server}.${tool}` : null;
}

export function DaemonRecordOpen({
  record,
  onShowCall,
}: {
  record: ActivityRecord;
  onShowCall: (search: string) => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  if (record.source !== "daemon") return null;
  const lines = daemonContinuation(record.log);
  const call = callSearchOf(record);
  const copy = () => {
    void navigator.clipboard
      ?.writeText(JSON.stringify(record.log.record, null, 2))
      .then(() => toast.success(t("activity.drawer.copied")))
      .catch(() => toast.error(t("activity.drawer.copyFailed")));
  };
  return (
    <div className="flex flex-col gap-2">
      <pre className="m-0 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border-subtle bg-surface-sunken px-3.5 py-3 font-mono text-xs leading-[1.6] text-text">
        {lines.length ? lines.join("\n") : describeDaemonRecord(t, record.log)}
      </pre>
      <div className="flex gap-2">
        {call ? (
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onShowCall(call);
            }}
          >
            <Server />
            {t("activity.daemonLog.showCall")}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            copy();
          }}
        >
          <Copy />
          {t("activity.drawer.copyRecord")}
        </Button>
      </div>
    </div>
  );
}
