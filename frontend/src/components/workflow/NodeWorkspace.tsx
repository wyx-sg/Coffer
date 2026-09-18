// frontend/src/components/workflow/NodeWorkspace.tsx
// Everything under a task's header: the transcript, what the task is working
// from, and the one box you type into (FR-029, FR-063).
//
// THE COMPOSER SPANS BOTH COLUMNS. What you type is addressed to the TASK, not
// to the left-hand column, and a box that stopped at the panel's edge said the
// panel was a different place. It is also the widest thing on the page for the
// most ordinary of reasons: it is where the sentences go.
//
// The divider between them DRAGS, and the width is remembered per browser. A
// transcript and a file want opposite amounts of room, the same developer
// wants each at different moments, and any number this file picked would be
// wrong for one of them.
//
// The panel also OPENS AND CLOSES, at any width. It used to appear only above
// `lg` and vanish below it with no way to ask for it back, so on a narrower
// window the run's files were simply unreachable from the conversation that
// talks about them. Wide enough and it sits beside the transcript; narrower
// and it covers it, because a panel that only exists on big screens is a panel
// half the people never see.
//
// The turn lives here rather than in the thread because the composer is out
// here now: the send, the stop and the streaming flag are one state, and
// splitting them across two components would mean passing them back up.
//
// The AGENT, MODEL and EFFORT bar is the chat layer's own, unchanged. A task's
// conversation is an ordinary Coffer conversation (FR-019/FR-030), so the
// developer who wants this one on a bigger model, or thinking harder, changes
// it exactly where they would in Chat — and a second set of pickers that wrote
// the same three fields would eventually disagree with the first.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PanelRight } from "lucide-react";

import { AgentModelBar } from "@/components/chat/AgentModelBar";
import { Button } from "@/components/ui/button";
import { Composer } from "@/components/chat/Composer";
import { NodeContextRail } from "@/components/workflow/NodeContextRail";
import { NodeThread } from "@/components/workflow/NodeThread";
import { TaskBrief } from "@/components/workflow/TaskBrief";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useChatTurn } from "@/lib/hooks/useChatTurn";
import { useConversation } from "@/lib/hooks/useConversations";

/** Where the divider was left. Per browser and per person, like every other
 *  reading convenience — it never leaves this machine and nothing depends on
 *  it being there. */
const REMEMBERED = "coffer.workflow.contextWidth";
const SHOWN = "coffer.workflow.contextOpen";
const MIN = 220;
const MAX = 620;
const DEFAULT = 320;

function rememberedOpen(): boolean {
  try {
    return localStorage.getItem(SHOWN) !== "0";
  } catch {
    return true;
  }
}

function remembered(): number {
  try {
    const raw = Number(localStorage.getItem(REMEMBERED));
    return Number.isFinite(raw) && raw >= MIN && raw <= MAX ? raw : DEFAULT;
  } catch {
    // Private windows and blocked site data both throw here, and a page that
    // could not read a width is a page that uses the default one.
    return DEFAULT;
  }
}

interface Props {
  runId: string;
  /** Null until the task has started; a manual task never gets one. */
  conversationId: string | null;
  attemptId: string | null | undefined;
  ownedHere: boolean;
  /** False only while the task has never run. */
  started: boolean;
  /** What the task has been told so far (FR-068). */
  instructions: string | null | undefined;
  /**
   * Where a typed sentence goes. Null means "into the conversation", which is
   * only right while a turn is in flight: the agent is reading it and the
   * message queues server-side. Every other state hands it to the engine.
   */
  onSay: ((text: string) => void) | null;
  saying: boolean;
}

export function NodeWorkspace({
  runId,
  conversationId,
  attemptId,
  ownedHere,
  started,
  instructions,
  onSay,
  saying,
}: Props) {
  const { t } = useTranslation();
  const turn = useChatTurn(conversationId ?? "");
  const conversation = useConversation(conversationId ?? "");
  const agentKey = conversation.data?.agent_key;
  const agentLabel = (useAgentProviders().data ?? []).find(
    (a) => a.agent_key === agentKey,
  )?.display_name;
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(remembered);
  const [open, setOpen] = useState(rememberedOpen);
  const [dragging, setDragging] = useState(false);

  const onDrag = useCallback((event: PointerEvent) => {
    const box = frame.current?.getBoundingClientRect();
    if (box === undefined) return;
    setWidth(Math.min(MAX, Math.max(MIN, box.right - event.clientX)));
  }, []);

  useEffect(() => {
    if (!dragging) return;
    const stop = () => setDragging(false);
    window.addEventListener("pointermove", onDrag);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", onDrag);
      window.removeEventListener("pointerup", stop);
    };
  }, [dragging, onDrag]);

  useEffect(() => {
    try {
      localStorage.setItem(REMEMBERED, String(width));
      localStorage.setItem(SHOWN, open ? "1" : "0");
    } catch {
      // Nothing depends on it being stored; both are already applied.
    }
  }, [width, open]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {agentKey === undefined ? null : (
        <AgentModelBar
          conversationId={conversationId ?? ""}
          agentKey={agentKey}
          agentLabel={agentLabel ?? agentKey}
          disabled={!ownedHere}
        />
      )}

      <div ref={frame} className="relative flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          {conversationId === null ? (
            <TaskBrief instructions={instructions} started={started} />
          ) : (
            <NodeThread
              conversationId={conversationId}
              runId={runId}
              attemptId={attemptId}
              turn={turn}
            />
          )}
        </div>

        {open ? (
          <>
            {/* A one-pixel line to look at and eight to hit: a divider you have
                to aim for is a divider nobody moves. Only where there is room
                to drag it — over the transcript there is nothing to trade. */}
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label={t("workflow.context.resize")}
              onPointerDown={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              className={`hidden w-2 shrink-0 cursor-col-resize border-l border-border transition-colors hover:border-primary lg:block ${
                dragging ? "border-primary" : ""
              }`}
            />
            {/* Beside the transcript when there is room, over it when there is
                not. `absolute inset-y-0 right-0` is the narrow case. */}
            <div
              className="absolute inset-y-0 right-0 z-10 w-[min(22rem,100%)] bg-background shadow-lg lg:relative lg:z-0 lg:w-auto lg:shrink-0 lg:shadow-none"
              style={{ width: undefined }}
            >
              <div
                className="h-full lg:w-[var(--context-w)]"
                style={{ ["--context-w" as string]: `${width}px` }}
              >
                <NodeContextRail runId={runId} onClose={() => setOpen(false)} />
              </div>
            </div>
          </>
        ) : null}
      </div>

      <div className="flex shrink-0 items-end gap-2 border-t border-border px-6 py-3">
        {open ? null : (
          <Button variant="outline" size="sm" className="shrink-0" onClick={() => setOpen(true)}>
            <PanelRight className="mr-1 size-3.5" aria-hidden />
            {t("workflow.tabs.context")}
          </Button>
        )}
        <div className="min-w-0 flex-1">
          {ownedHere ? (
            // Never disabled by streaming: a message sent mid-turn queues
            // server-side, and a node's turn can run for hours.
            <Composer
              onSend={onSay ?? ((text) => void turn.send(text))}
              disabled={saying && onSay !== null && conversationId === null}
              streaming={turn.isStreaming}
              onStop={() => void turn.interrupt()}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("workflow.nodeConversation.readOnly")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
