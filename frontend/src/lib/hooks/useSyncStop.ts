// frontend/src/lib/hooks/useSyncStop.ts
//
// What a round asks of a person (spec vault-sync): the files a stopped round
// could not merge, the deletions the breaker held, and the join a machine
// makes the first time it meets the remote.
//
// Each route answers the ONE situation the daemon is holding — none of them
// names a round — so the queries here are gated by the status saying there is
// something to answer, and every answer invalidates the whole sync tree: an
// answered file changes the stop, a continued round changes the status, the
// history and the vault.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import { syncApi, type ConflictAnswer, type HandoffRequest, type JoinChoice } from "@/lib/api/sync";
import { syncKey } from "@/lib/api/queryKeys";
import { invalidateSync } from "@/lib/syncInvalidate";
import { isApprovalWait } from "@/lib/syncApproval";
import { useToast } from "@/components/ui/toast";
import { useRoundMutation } from "@/lib/hooks/useSync";

const syncStopKey = [...syncKey, "stop"] as const;
const syncJoinPreviewKey = [...syncKey, "join-preview"] as const;
const syncJoinChoicesKey = [...syncKey, "join-choices"] as const;

/** The stopped round, while the status says one is. */
export function useSyncStop(enabled: boolean) {
  return useQuery({ queryKey: syncStopKey, queryFn: () => syncApi.stop(), enabled });
}

/**
 * Answer one file. No error toast: the row that asked shows the refusal in
 * place — above all `SYNC_CONFLICT_MARKERS_LEFT`, whose message names the line
 * the person still has to fix.
 */
export function useAnswerFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, answer }: { path: string; answer: ConflictAnswer }) =>
      syncApi.answerFile(path, answer),
    onSuccess: () => invalidateSync(qc),
  });
}

/**
 * "Open in editor": the daemon writes a copy with conflict markers, then the
 * OS opens it. Two calls, one click — the copy has to exist before anything
 * can open it. `join` asks for a first join's differing file instead of a
 * stopped round's.
 */
export function useOpenInEditor({ join = false } = {}) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (path: string) => {
      const copy = await (join ? syncApi.joinEditorCopy(path) : syncApi.editorCopy(path));
      await fsApi.open(copy.editor_path);
      return copy;
    },
    onSuccess: () => invalidateSync(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * "Back to two choices": forget the marked-up copy, an agent's hand-off or
 * merge, and any answer for one file. Whatever was written in the copy is gone.
 */
export function useDiscardCopy({ join = false } = {}) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (path: string) => {
      await (join ? syncApi.discardJoinCopy(path) : syncApi.discardCopy(path));
    },
    onSuccess: () => invalidateSync(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Hand files to an agent. Not a mutation hook: `AgentHandoff` calls it when the
 * person picks Hand off to <Agent> or Copy prompt, and the files then read as handed
 * over, so the sync tree is refetched. Omit `paths` for every file an agent may merge.
 */
export function useHandoffRequest({ join = false } = {}) {
  const qc = useQueryClient();
  return async (body: HandoffRequest = {}): Promise<string> => {
    const out = await (join ? syncApi.joinHandoff(body) : syncApi.handoff(body));
    invalidateSync(qc);
    return out.handoff.prompt;
  };
}

/** Both sides of one file and what taking theirs changes — fetched on demand. */
export function useFileVersions(path: string, enabled: boolean) {
  return useQuery({
    queryKey: [...syncStopKey, "versions", path],
    queryFn: () => syncApi.fileVersions(path),
    enabled,
  });
}

/** Finish the stopped round once every file is answered. */
export function useContinueRound() {
  return useRoundMutation<void>(() => syncApi.continueRound());
}

/** Apply the held deletions, and continue. The view shows a refusal in place. */
export function useConfirmHold() {
  return useRoundMutation<void>(() => syncApi.confirmHold(), { toastErrors: false });
}

/** Keep the files the round would have deleted, and continue. */
export function useRestoreHold() {
  return useRoundMutation<void>(() => syncApi.restoreHold(), { toastErrors: false });
}

/** What joining would do, applying nothing — asked while this machine has not joined. */
export function useJoinPreview(enabled: boolean) {
  return useQuery({
    queryKey: syncJoinPreviewKey,
    queryFn: () => syncApi.joinPreview(),
    enabled,
    // The push token can wait for approval in the desktop app: ask again when
    // the person comes back to this window, and meanwhile every few seconds.
    refetchOnWindowFocus: true,
    refetchInterval: (query) => (isApprovalWait(query.state.error) ? 5_000 : false),
  });
}

/** Join the remote, after its preview was shown. */
export function useJoin() {
  return useRoundMutation<void>(() => syncApi.join());
}

/** The files a join left differing here, while the status counts any. */
export function useJoinChoices(enabled: boolean) {
  return useQuery({ queryKey: syncJoinChoicesKey, queryFn: () => syncApi.joinChoices(), enabled });
}

/**
 * Answer some or all of the join's differing files. A refusal (a marker left
 * in an edited copy) is shown in place by the caller, like `useAnswerFile`'s.
 */
export function useChooseJoin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (choices: JoinChoice[]) => syncApi.chooseJoin(choices),
    onSuccess: () => invalidateSync(qc),
  });
}
