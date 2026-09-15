// frontend/src/pages/AgentConversationPage.tsx — spec agent-registry FR-047.
// One of the agent's past conversations, reached by clicking its row on the
// Conversations tab: the session's header (title, project, counts, times), the
// open-in-editor / reveal actions, and the turns themselves.
//
// The session is addressed by `?path=` — the absolute `source_path` the listing
// gave the row — because that file IS the session's identity: `session_id`
// repeats across subagent sidechain files, so keying a page by it would
// sometimes show the wrong conversation. Keeping it in the URL rather than in
// router state also means the page survives a reload and can be linked to.
//
// Not a tree, unlike the memory-store page next door: one session is one file,
// so there is nothing to browse — the only structure worth showing is the
// dialogue itself.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";

import { AgentTranscriptOutline } from "@/components/agents/AgentTranscriptOutline";
import { AgentTranscriptView } from "@/components/agents/AgentTranscriptView";
import { FileActions } from "@/components/FileActions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { TRANSCRIPT_TURNS_PAGE_SIZE, useTranscriptSession } from "@/lib/hooks/useAgentTranscripts";

export function AgentConversationPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const sourcePath = useSearchParams()[0].get("path") ?? "";
  const [offset, setOffset] = useState(0);
  const { data, isPending, error } = useTranscriptSession(name, sourcePath, offset);

  const backToTab = () => navigate(`/agents/${encodeURIComponent(name)}?tab=conversations`);

  const back = (
    <div className="-ml-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={backToTab}
        className="text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" />
        {t("common.backTo", { label: t("agents.workspace.conversations") })}
      </Button>
    </div>
  );

  if (isPending) {
    return (
      <div className="space-y-6">
        {back}
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="space-y-6">
        {back}
        <Card className="border-destructive/40">
          <CardContent className="space-y-3 py-6">
            <p className="text-sm text-destructive" role="alert">
              {error ? translateApiError(t, error) : t("agents.conversationDetail.loadFailed")}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const shown = data.messages.length;
  const hasMore = data.offset + shown < data.message_count;

  return (
    <div className="space-y-6">
      {back}

      <header className="space-y-2">
        <h1 className="font-serif text-2xl tracking-tight">{data.title ?? data.session_id}</h1>
        {data.project_path ? (
          <p className="font-mono text-xs text-muted-foreground">{data.project_path}</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {/* The window and the whole are separate numbers on purpose: a reader
              looking at the first 200 turns of 812 should be told so. */}
          {t("agents.conversationDetail.turnRange", {
            from: data.offset + 1,
            to: data.offset + shown,
            total: data.message_count,
          })}
          {data.last_activity_at ? ` · ${new Date(data.last_activity_at).toLocaleString()}` : ""}
        </p>
        <FileActions filePath={data.source_path} />
      </header>

      {/* Contents on the left, the conversation in its own frame on the right
          — the same two-pane shape every other detail surface here uses. The
          outline indexes the loaded window, which is what the header's turn
          range already says the reader is looking at. */}
      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        <AgentTranscriptOutline messages={data.messages} />
        <AgentTranscriptView messages={data.messages} />
      </div>

      {/* Paging the turns, not the sessions — the transcript can be far longer
          than one window, and the whole file is never fetched at once. */}
      {offset > 0 || hasMore ? (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - TRANSCRIPT_TURNS_PAGE_SIZE))}
          >
            {t("agents.conversationDetail.earlier")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasMore}
            onClick={() => setOffset((o) => o + TRANSCRIPT_TURNS_PAGE_SIZE)}
          >
            {t("agents.conversationDetail.later")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
