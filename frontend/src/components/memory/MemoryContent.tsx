// frontend/src/components/memory/MemoryContent.tsx
//
// One memory's body, shared by the drawer and the full-width reader (spec
// memory "Manage memory sync in the web UI and on the command line"). First,
// where each agent on this machine holds it — one line per agent: its copy's
// state (its own file, written, waiting, held back, removed by the agent…),
// the file's path, and Open / Reveal as icon buttons — so it never sinks under
// a long memory; past `LOCATIONS_SHOWN` agents the rest fold under "N more".
// Then the memory's text, read only, without a first heading that only
// repeats the title.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { LoadError } from "@/components/LoadError";
import { Markdown } from "@/components/Markdown";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TruncatedPath } from "@/components/ui/truncated-text";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { EntryCopy } from "@/lib/api/memoryTypes";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useMemoryEntry } from "@/lib/hooks/useMemory";
import { copyState, copyStateTone } from "@/lib/memory/syncFacts";

/** Agents listed before the rest fold under "N more". */
const LOCATIONS_SHOWN = 4;

/** The body without a leading heading that only repeats the title. */
function withoutTitle(body: string, title: string): string {
  const match = /^\s*#{1,6}\s+(.+?)\s*\n/.exec(body);
  if (match && match[1].trim().toLowerCase() === title.trim().toLowerCase()) {
    return body.slice(match[0].length);
  }
  return body;
}

function FileButtons({ path }: { path: string }) {
  const items = useFileActionItems(path);
  return (
    <span className="flex shrink-0 items-center">
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <Tooltip key={it.key}>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={it.label}
                onClick={it.onClick}
              >
                <Icon aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{it.label}</TooltipContent>
          </Tooltip>
        );
      })}
    </span>
  );
}

function Location({ copy }: { copy: EntryCopy }) {
  const { t } = useTranslation();
  const state = copyState(copy.state);
  return (
    <li className="flex h-9 min-w-0 items-center gap-3 px-3">
      <span className="w-[120px] shrink-0">
        <AgentBadge
          type={copy.agent_type}
          name={agentTypeLabel(copy.agent_type)}
          size="sm"
          showName
        />
      </span>
      <span className="w-[96px] shrink-0">
        {state ? (
          <StatusWord tone={copyStateTone(state)}>{t(`memory.copy.${state}`)}</StatusWord>
        ) : (
          <StatusWord tone="off">{copy.state}</StatusWord>
        )}
      </span>
      {copy.path ? (
        <>
          <TruncatedPath
            text={abbreviateHomePath(copy.path)}
            className="min-w-0 flex-1 font-mono text-2xs text-text-muted"
          />
          <FileButtons path={copy.path} />
        </>
      ) : (
        <span className="flex-1" />
      )}
    </li>
  );
}

export function MemoryContent({ id, title }: { id: string; title: string }) {
  const { t } = useTranslation();
  const detail = useMemoryEntry(id);
  const [allShown, setAllShown] = useState(false);

  if (detail.error) {
    return <LoadError error={detail.error} onRetry={() => void detail.refetch()} />;
  }
  if (detail.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    );
  }
  const copies = detail.data.copies;
  const shown = allShown ? copies : copies.slice(0, LOCATIONS_SHOWN);
  const hidden = copies.length - shown.length;

  return (
    <div className="flex flex-col gap-5">
      <section aria-label={t("memory.drawer.inAgents")} data-testid="memory-locations">
        <ul className="flex flex-col divide-y divide-border-subtle rounded-lg border border-border-subtle">
          {shown.map((c) => (
            <Location key={c.agent_type} copy={c} />
          ))}
          {hidden > 0 ? (
            <li>
              <button
                type="button"
                className="h-8 w-full px-3 text-left text-xs text-text-muted hover:text-text"
                onClick={() => setAllShown(true)}
              >
                {t("memory.drawer.more", { count: hidden })}
              </button>
            </li>
          ) : null}
        </ul>
      </section>
      <Markdown>{withoutTitle(detail.data.body, title)}</Markdown>
    </div>
  );
}
