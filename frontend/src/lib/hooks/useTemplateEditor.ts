// frontend/src/lib/hooks/useTemplateEditor.ts — the template being authored.
//
// THERE IS NO DRAFT. Every edit is applied to what the server has and written
// back immediately, so the page never holds unsaved state and there is nothing
// to discard. What used to be a Save button over a form with forty inputs in
// it is now the Save inside the dialog that made the change: a task's dialog
// holds what is being typed until it is saved, and everything on the map —
// adding, reordering, deleting — is a single act that persists as it happens.
//
// That removes the failure this page used to have. A draft that adopts the
// server's version "only while it is clean" is a rule that is wrong in both
// directions: leave the tab open and your edits are stale, or lose them to a
// refetch. With no draft there is nothing to reconcile.
//
// It introduces a different one, which is what the two rules below are for.
// With no draft, an edit is a function of what is CURRENTLY stored — so two
// edits that overlap must not both be computed from the same starting point,
// or the second silently undoes the first. The settings fields make that
// reachable with ordinary typing: they save on blur and have no in-flight
// guard, so leaving one field and the next within a few milliseconds fires
// two saves before either has come back. Hence:
//
//   1. **Read at call time, not at render time.** The config comes out of the
//      query cache when `apply` runs, not out of the closure of whichever
//      render installed the handler.
//   2. **One at a time.** Applies are chained, so each one reads the cache
//      after the previous one has written its result into it (which
//      `useSaveWorkflowTemplate` does on success, before the refetch).
import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { resourceKey } from "@/lib/api/queryKeys";
import type { TemplateConfig } from "@/lib/api/workflow";
import { useSaveWorkflowTemplate, type WorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";

export interface TemplateEditor {
  /** Apply a pure edit and write the result. Resolves when the daemon has
   *  taken it; REJECTS when it refused, so a dialog can stay open on its
   *  refusal rather than closing over one. */
  apply: (edit: (config: TemplateConfig) => TemplateConfig) => Promise<void>;
  isSaving: boolean;
  /** The last refusal, for edits made outside a dialog. */
  error: unknown;
  /** Forget a refusal — called when a dialog opens, so it does not inherit
   *  the message from something the developer already moved on from. */
  reset: () => void;
}

export function useTemplateEditor(uid: string): TemplateEditor {
  const qc = useQueryClient();
  const save = useSaveWorkflowTemplate();
  const { mutateAsync, reset } = save;
  // The tail of the chain. A rejected link is caught here so one refused edit
  // does not poison every edit after it — the refusal is the caller's, and it
  // already has it from the promise `apply` returned.
  const queue = useRef<Promise<void>>(Promise.resolve());

  const apply = useCallback(
    (edit: (config: TemplateConfig) => TemplateConfig) => {
      const next = queue.current.then(
        async () => {
          const stored = qc.getQueryData<WorkflowTemplate>(resourceKey(uid));
          if (stored === undefined) return;
          const config = edit(stored.config);
          // The description lives on the resource as well as in the config,
          // and the two have to agree: a template whose list row says one
          // thing and whose config says another has two descriptions.
          await mutateAsync({ uid, description: config.description ?? null, config });
        },
        // The previous edit failed; this one still gets its turn.
        async () => {},
      );
      queue.current = next.catch(() => {});
      return next;
    },
    [qc, mutateAsync, uid],
  );

  return { apply, isSaving: save.isPending, error: save.error, reset };
}
