// frontend/src/pages/sync/useResolveSource.ts
//
// One page, two sources: the files a stopped round could not merge (answers
// are recorded as they are picked, written into the vault by Continue round)
// and the files a first join left differing (choices are staged here and sent
// together by Apply choices; Mark resolved on an edited copy is sent at once,
// because it is the one answer the daemon can refuse). The Resolve page's
// panes read this, so they never ask which of the two they are showing.
import { useState } from "react";

import type { ConflictAnswer, ConflictFile, HandoffRequest } from "@/lib/api/sync";
import {
  useAnswerFile,
  useChooseJoin,
  useContinueRound,
  useDiscardCopy,
  useHandoffRequest,
  useJoinChoices,
  useOpenInEditor,
  useSyncStop,
} from "@/lib/hooks/useSyncStop";

export type ResolveMode = "conflicts" | "join";
type Side = "mine" | "theirs";

export interface ResolveSource {
  mode: ResolveMode;
  loading: boolean;
  files: ConflictFile[];
  /** When the round stopped; null for a join. */
  raisedAt: string | null;
  /** How many files have a version picked (join: staged, not yet applied). */
  chosen: number;
  choose: (path: string, answer: Side) => void;
  /** Take the saved copy as the file's version (refused while a marker is left in it). */
  markResolved: (path: string) => void;
  openEditor: (path: string, onOpened: () => void) => void;
  /** Back to two choices. */
  discard: (path: string, onDone?: () => void) => void;
  /** The prompt for an agent; resolves once the files are recorded as handed over. */
  handoff: (body?: HandoffRequest) => Promise<string>;
  /** An answer is in flight. */
  busy: boolean;
  editorBusy: boolean;
  /** The last answer's refusal, to show in place. */
  error: unknown;
  /** The foot's button: Continue round (a stop) or Apply choices (a join). */
  finish: {
    ready: boolean;
    pending: boolean;
    run: (onDone: () => void) => void;
  };
}

export function useResolveSource(mode: ResolveMode): ResolveSource {
  const join = mode === "join";
  const stop = useSyncStop(!join);
  const choices = useJoinChoices(join);
  const joined = useChooseJoin();
  const answer = useAnswerFile();
  const proceed = useContinueRound();
  const editor = useOpenInEditor({ join });
  const discard = useDiscardCopy({ join });
  const handoff = useHandoffRequest({ join });
  const [staged, setStaged] = useState<Record<string, Side>>({});

  const round =
    !join && stop.data?.stopped && stop.data.round?.kind === "conflicts" ? stop.data.round : null;
  const raw: ConflictFile[] = join ? (choices.data?.files ?? []) : (round?.files ?? []);
  const files = join ? raw.map((f) => ({ ...f, answer: staged[f.path] ?? f.answer })) : raw;
  const chosen = files.filter((f) => f.answer !== null).length;

  const unstage = (path: string) =>
    setStaged((prev) => Object.fromEntries(Object.entries(prev).filter(([p]) => p !== path)));

  return {
    mode,
    loading: join ? choices.isLoading : stop.isLoading,
    files,
    raisedAt: round?.raised_at ?? null,
    chosen,
    choose: (path, side) => {
      if (join) {
        joined.reset();
        setStaged((prev) => ({ ...prev, [path]: side }));
      } else {
        answer.mutate({ path, answer: side });
      }
    },
    markResolved: (path) => {
      if (join) joined.mutate([{ path, answer: "edited" }], { onSuccess: () => unstage(path) });
      else answer.mutate({ path, answer: "edited" });
    },
    openEditor: (path, onOpened) => {
      answer.reset();
      joined.reset();
      editor.mutate(path, { onSuccess: onOpened });
    },
    discard: (path, onDone) => {
      answer.reset();
      joined.reset();
      unstage(path);
      discard.mutate(path, { onSuccess: onDone });
    },
    handoff: (body) => handoff(body),
    busy: join ? joined.isPending : answer.isPending,
    editorBusy: editor.isPending || discard.isPending,
    error: join ? joined.error : answer.error,
    finish: join
      ? {
          ready: chosen > 0,
          pending: joined.isPending,
          run: (onDone) => {
            const picks = files
              .filter((f) => staged[f.path])
              .map((f) => ({ path: f.path, answer: staged[f.path] as ConflictAnswer }));
            joined.mutate(picks, {
              onSuccess: (left) => {
                setStaged({});
                if (left.files.length === 0) onDone();
              },
            });
          },
        }
      : {
          ready: !!round && round.unanswered === 0,
          pending: proceed.isPending,
          run: (onDone) => proceed.mutate(undefined, { onSuccess: onDone }),
        },
  };
}
