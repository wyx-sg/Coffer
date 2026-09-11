// frontend/src/components/FileEditor.tsx — specs agent-registry / skill-manager.
// The in-app editor for a file that also lives on the user's disk: agent config
// files and skill master files both use it.
//
// Editing is an explicit mode, not the default. These files are the agent's
// real configuration and the skill's real content — a stray keystroke in a
// pane the user opened to *look* at something should not be able to change
// them, and for markdown the rendered view is the more useful default anyway.
// So the pane reads, and an Edit button turns it into a textarea with Save and
// Cancel.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";

export interface FileEditorProps {
  /** The draft (in edit mode) or the loaded content (otherwise). */
  value: string;
  onChange: (value: string) => void;
  editing: boolean;
  dirty: boolean;
  saving: boolean;
  /** Save rejected — a stale conflict or a format error. */
  error: unknown;
  /** True when `error` is the daemon refusing a stale write. */
  conflict: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  /** Takes the daemon's copy, discarding the draft. */
  onDiscardAndReload: () => void;
  /** Set when the file cannot be edited safely; the reason is shown instead of
   *  the Edit button. A binary file, or one the read truncated — saving a
   *  partial read would cut the file short on disk. */
  readOnlyReason?: string | null;
  ariaLabel: string;
  /** Rendered in place of the textarea when not editing. */
  children: React.ReactNode;
}

export function FileEditor(props: FileEditorProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-2">
        {props.readOnlyReason ? (
          <span className="text-xs text-muted-foreground">{props.readOnlyReason}</span>
        ) : props.editing ? (
          <>
            <Button variant="ghost" size="sm" onClick={props.onCancel} disabled={props.saving}>
              {t("common.cancel")}
            </Button>
            <Button size="sm" onClick={props.onSave} disabled={!props.dirty || props.saving}>
              {props.saving ? t("common.saving") : t("common.save")}
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={props.onEdit}>
            {t("common.edit")}
          </Button>
        )}
      </div>

      {props.error ? (
        <div
          role="alert"
          className="space-y-2 rounded border border-destructive/50 bg-destructive/10 px-2 py-1.5 text-xs text-destructive"
        >
          <p>
            {props.conflict
              ? t("files.conflict")
              : translateApiError(t, props.error)}
          </p>
          {props.conflict ? (
            <Button variant="outline" size="sm" onClick={props.onDiscardAndReload}>
              {t("files.discardAndReload")}
            </Button>
          ) : null}
        </div>
      ) : null}

      {props.editing ? (
        <textarea
          aria-label={props.ariaLabel}
          className="h-[60vh] w-full resize-y rounded border bg-background p-3 font-mono text-xs leading-relaxed outline-none focus-visible:ring-1 focus-visible:ring-ring"
          value={props.value}
          spellCheck={false}
          onChange={(e) => props.onChange(e.target.value)}
        />
      ) : (
        props.children
      )}
    </div>
  );
}
