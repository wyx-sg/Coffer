// frontend/src/pages/sync/SyncConflictChoices.tsx
//
// The two choices for one file (6.5.06, 6.5.24): Keep this Mac's or Take the
// other Mac's. Picking one records it as the file's answer at once — nothing
// is written into the vault until the round continues — and what it changes
// here shows under the cards: the diff from this Mac's version to theirs, or
// that nothing changes here. A refusal is shown in place.
//
// An encrypted secret shows no diff: a one-line note says its contents are not
// shown. A file an agent may merge carries the "Merge with an agent" block
// under the choices while it has no answer.
import { useTranslation } from "react-i18next";

import type { ConflictAnswer, ConflictFile } from "@/lib/api/sync";
import { cn } from "@/lib/utils";
import { SyncConflictDiff } from "./SyncConflictDiff";
import { SyncConflictMerge } from "./SyncConflictMerge";
import { otherMachine, refusal, when } from "./syncConflictFormat";

interface Props {
  file: ConflictFile;
  handoff: string | null;
  pending: boolean;
  error: unknown;
  onChoose: (answer: ConflictAnswer) => void;
}

function Choice(props: {
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={props.checked}
      aria-label={props.label}
      disabled={props.disabled}
      onClick={props.onPick}
      className={cn(
        "flex min-w-0 flex-1 basis-0 items-start gap-2.5 rounded-lg border bg-surface-raised p-3 text-left transition-colors duration-fast disabled:opacity-60",
        props.checked ? "border-accent ring-1 ring-accent" : "border-border hover:bg-surface-hover",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-flex size-4 shrink-0 items-center justify-center rounded-full border",
          props.checked ? "border-transparent bg-accent" : "border-border bg-surface-raised",
        )}
      >
        {props.checked ? <span className="size-1.5 rounded-full bg-on-accent" /> : null}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{props.label}</span>
        <span className="text-xs leading-[1.45] text-text-muted">{props.hint}</span>
      </span>
    </button>
  );
}

export function SyncConflictChoices({ file, handoff, pending, error, onChoose }: Props) {
  const { t, i18n } = useTranslation();
  const machine = otherMachine(t, file);
  const mineWhen = when(t, file.ours_time, i18n.language);
  const theirsWhen = when(t, file.theirs_time, i18n.language);
  const note = "text-xs text-text-muted";

  return (
    <>
      <div role="radiogroup" className="flex gap-2">
        <Choice
          label={t("sync.resolve.keepMine")}
          hint={
            mineWhen
              ? t("sync.resolve.keepMineHint", { when: mineWhen, machine })
              : t("sync.resolve.keepMineHintBare", { machine })
          }
          checked={file.answer === "mine"}
          disabled={pending}
          onPick={() => onChoose("mine")}
        />
        <Choice
          label={t("sync.resolve.takeTheirs", { machine })}
          hint={
            theirsWhen
              ? t("sync.resolve.takeTheirsHint", { when: theirsWhen })
              : t("sync.resolve.takeTheirsHintBare")
          }
          checked={file.answer === "theirs"}
          disabled={pending}
          onPick={() => onChoose("theirs")}
        />
      </div>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {refusal(t, error)}
        </p>
      ) : null}
      {file.secret ? (
        <p className={note} data-testid="sync-conflict-secret">
          {t("sync.resolve.secret")}
        </p>
      ) : file.answer === "theirs" ? (
        <SyncConflictDiff path={file.path} />
      ) : file.answer === "mine" ? (
        <p className="text-sm text-text">{t("sync.resolve.nothingChanges", { machine })}</p>
      ) : null}
      {file.answer === "edited" ? (
        <p className={note}>{t("sync.resolve.resolvedInEditor")}</p>
      ) : (
        <p className={note}>{t("sync.resolve.flipNote")}</p>
      )}
      {file.agent_merge && !file.secret && handoff && file.answer === null ? (
        <SyncConflictMerge prompt={handoff} />
      ) : null}
    </>
  );
}
