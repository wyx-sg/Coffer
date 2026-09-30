// frontend/src/pages/sync/SyncRemoteFields.tsx
//
// The remote's fields, shared by first-run setup (6.5.16) and the Remote tab
// (6.5.22): Repository URL; Branch beside Secret; User name, for an HTTPS URL
// only; Run a round; Include encrypted secrets.
//
// Presentational — it owns no draft and saves nothing. Every edit reaches the
// parent as `onEdit(patch, commit)`: text fields send each keystroke with
// `commit: false` and their blur with `commit: true`; pickers and the switch
// always commit. Setup ignores `commit` (it saves behind Check repository);
// the Remote tab saves on it.
//
// There is deliberately no password field: the remote names its secret by
// reference, so a secret has no reason to exist in this component's tree.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SyncIncludeSecrets } from "./SyncIncludeSecrets";
import { SyncRoundCadence } from "./SyncRoundCadence";
import { SyncSecretPicker } from "./SyncSecretPicker";
import { isHttpsUrl, type FormErrors, type FormState } from "./syncRemoteForm";

interface Props {
  form: FormState;
  onEdit: (patch: Partial<FormState>, commit: boolean) => void;
  errors: FormErrors;
  busy: boolean;
  /** How many encrypted secrets this vault holds — what the switch would push. */
  secrets: number;
  /** First run: the longer hints under each field. */
  setup?: boolean;
  /** Ask before including secrets — the remote is stored. */
  confirmSecrets?: boolean;
  /** Open the secret picker on mount (`?focus=secret`). */
  focusSecret?: boolean;
}

function Field({
  id,
  label,
  hint,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className ?? "flex flex-col gap-1.5"}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function SyncRemoteFields(props: Props) {
  const { form, onEdit, errors, busy, secrets, setup = false } = props;
  const { t } = useTranslation();
  const text = (key: "url" | "branch" | "username") => ({
    value: form[key],
    disabled: busy,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => onEdit({ [key]: e.target.value }, false),
    onBlur: () => onEdit({}, true),
    onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") e.currentTarget.blur();
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <Field
        id="sync-url"
        label={t("sync.remote.url")}
        hint={
          errors.url ? (
            <span className="text-danger" role="alert">
              {t(`sync.remote.errors.${errors.url}`)}
            </span>
          ) : setup ? (
            t("sync.setup.urlHint")
          ) : undefined
        }
      >
        <Input
          id="sync-url"
          className="font-mono"
          placeholder="git@github.com:you/coffer-vault.git"
          aria-invalid={errors.url ? true : undefined}
          {...text("url")}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Field id="sync-branch" label={t("sync.remote.branch")}>
          <Input id="sync-branch" className="font-mono" {...text("branch")} />
        </Field>
        <Field
          id="sync-secret"
          label={t("sync.remote.secret")}
          hint={setup ? t("sync.setup.secretHint") : t("sync.remote.secretHint")}
        >
          <SyncSecretPicker
            value={form.secretRef}
            disabled={busy}
            autoOpen={props.focusSecret}
            describedBy="sync-secret-hint"
            onChange={(secretRef) => onEdit({ secretRef }, true)}
          />
        </Field>
      </div>

      {isHttpsUrl(form.url) ? (
        <Field
          id="sync-username"
          label={t("sync.remote.username")}
          hint={t("sync.remote.usernameHint")}
        >
          <Input
            id="sync-username"
            placeholder="coffer"
            aria-describedby="sync-username-hint"
            {...text("username")}
          />
        </Field>
      ) : null}

      <Field
        id="sync-cadence"
        label={t("sync.remote.cadence.label")}
        hint={setup ? t("sync.setup.cadenceHint") : undefined}
      >
        <SyncRoundCadence
          id="sync-cadence"
          intervalSeconds={form.intervalSeconds}
          enabled={form.enabled}
          disabled={busy}
          onChange={(next) => onEdit(next, true)}
        />
      </Field>

      <div className="flex items-start justify-between gap-6 border-t border-border-subtle pt-4">
        <div className="flex max-w-[460px] flex-col gap-0.5">
          <Label htmlFor="sync-with-secret">{t("sync.remote.includeSecret")}</Label>
          <p id="sync-with-secret-hint" className="text-xs text-text-muted">
            {t("sync.remote.includeSecretHint")}
          </p>
        </div>
        <SyncIncludeSecrets
          id="sync-with-secret"
          checked={form.includeSecret}
          confirm={props.confirmSecrets ?? false}
          secrets={secrets}
          url={form.url}
          disabled={busy}
          describedBy="sync-with-secret-hint"
          onChange={(includeSecret) => onEdit({ includeSecret }, true)}
        />
      </div>
    </div>
  );
}
