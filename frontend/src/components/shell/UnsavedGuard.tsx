// frontend/src/components/shell/UnsavedGuard.tsx — the one guard for unsaved document edits (boards 1.1.12, 1.1.04).
// Spec web-ui "Guard unsaved edits when leaving a document editor".
// The one place leaving a document editor with unsaved edits is stopped and
// asked about. Editors register while dirty (`useUnsavedGuard`); this provider
// is mounted once around the shell and
//
//   • blocks every in-app navigation that changes the page (React Router's
//     `useBlocker`, which sees sidebar clicks, palette jumps, the title bar's
//     ← →, tab and file switches alike — they are all location changes), and
//   • asks the browser or the desktop window to confirm a close or reload.
//
// A blocked navigation opens "Leave without saving?": Discard changes goes on
// (the edits are dropped), Keep editing stays, Save and leave runs each
// editor's save and then goes on — a refused save stays here and says why.
// Opening or closing the Settings modal keeps the page mounted underneath, so
// it never counts as leaving.
import { useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { UNSAFE_DataRouterContext, useBlocker } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useBeforeUnload } from "@/lib/hooks/useBeforeUnload";
import {
  UnsavedGuardContext,
  type UnsavedEntry,
  type UnsavedRegistry,
} from "@/lib/hooks/useUnsavedGuard";
import { isSettingsPath } from "@/lib/navigation";

export function UnsavedGuardProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<ReadonlyMap<string, UnsavedEntry>>(new Map());
  const registry = useMemo<UnsavedRegistry>(
    () => ({
      register: (id, entry) => {
        setEntries((prev) => new Map(prev).set(id, entry));
        return () =>
          setEntries((prev) => {
            const next = new Map(prev);
            next.delete(id);
            return next;
          });
      },
    }),
    [],
  );
  // `useBlocker` needs a data router. The app always has one; a bare
  // MemoryRouter (a component test) has none, and then only the window
  // listener applies.
  const dataRouter = useContext(UNSAFE_DataRouterContext) !== null;
  useBeforeUnload(entries.size > 0);
  return (
    <UnsavedGuardContext.Provider value={registry}>
      {children}
      {dataRouter ? <LeaveGuard entries={entries} /> : null}
    </UnsavedGuardContext.Provider>
  );
}

function LeaveGuard({ entries }: { entries: ReadonlyMap<string, UnsavedEntry> }) {
  const { t } = useTranslation();
  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (entriesRef.current.size === 0) return false;
    if (isSettingsPath(currentLocation.pathname) || isSettingsPath(nextLocation.pathname)) {
      return false;
    }
    return (
      currentLocation.pathname !== nextLocation.pathname ||
      currentLocation.search !== nextLocation.search
    );
  });
  const blocked = blocker.state === "blocked";
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!blocked) setError(null);
  }, [blocked]);

  // The dialog names the editor the user was last in; saving covers all of them.
  const first = [...entries.values()].pop();
  const keepEditing = () => blocker.state === "blocked" && !saving && blocker.reset();
  const discard = () => blocker.state === "blocked" && blocker.proceed();
  const saveAndLeave = async () => {
    setSaving(true);
    setError(null);
    try {
      for (const entry of entriesRef.current.values()) await entry.save();
      if (blocker.state === "blocked") blocker.proceed();
    } catch (e) {
      setError(e ?? new Error("save failed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={blocked && first !== undefined} onOpenChange={(next) => !next && keepEditing()}>
      <DialogContent className="max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{t("common.leaveGuard.title")}</DialogTitle>
          <DialogDescription>
            {t("common.leaveGuard.body", { file: first?.file, owner: first?.owner })}
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <DialogErrorBanner
            title={t("common.leaveGuard.saveFailed", { file: first?.file })}
            message={translateApiError(t, error)}
          />
        ) : null}
        <DialogFooter className="sm:justify-between">
          <Button variant="danger" disabled={saving} onClick={discard}>
            {t("common.leaveGuard.discard")}
          </Button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button variant="ghost" disabled={saving} onClick={keepEditing}>
              {t("common.leaveGuard.keep")}
            </Button>
            <Button loading={saving} onClick={() => void saveAndLeave()}>
              {saving ? t("common.saving") : t("common.leaveGuard.saveAndLeave")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
