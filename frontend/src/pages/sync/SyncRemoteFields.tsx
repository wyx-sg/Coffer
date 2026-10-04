// frontend/src/pages/sync/SyncRemoteFields.tsx
//
// The remote's rows, shared by first-run setup (6.4.20) and the Remote tab
// (6.4.27): Repository URL, Branch, Secret, User name (for an HTTPS URL only)
// and Run a round, as hairline rows in a "Remote" section. Include encrypted
// secrets joins the section in setup and gets its own section on the Remote tab
// (`SyncSecretsSection`).
//
// Presentational — it owns no draft and saves nothing. Every edit reaches the
// parent as `onEdit(patch, commit)`: text fields send each keystroke with
// `commit: false` and their blur with `commit: true`; pickers and the switch
// always commit. Setup ignores `commit` (it saves behind Check repository);
// the Remote tab saves on it.
//
// There is deliberately no password field: the remote names its secret by
// reference, so a secret has no reason to exist in this component's tree.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { SyncIncludeSecrets } from "./SyncIncludeSecrets";
import { SyncRoundCadence } from "./SyncRoundCadence";
import { SyncSecretPicker } from "./SyncSecretPicker";
import { SettingsRow, SettingsSection } from "./SyncSettingsParts";
import { isHttpsUrl, type FormErrors, type FormState } from "./syncRemoteForm";

interface Props {
  form: FormState;
  onEdit: (patch: Partial<FormState>, commit: boolean) => void;
  errors: FormErrors;
  busy: boolean;
  /** How many encrypted secrets this vault holds — what the switch would push. */
  secrets: number;
  /** First run: the longer hints, and the secrets switch inside this section. */
  setup?: boolean;
  /** Ask before including secrets — the remote is stored. */
  confirmSecrets?: boolean;
  /** Open the secret picker on mount (`?focus=secret`). */
  focusSecret?: boolean;
}

/** "Include encrypted secrets": the switch row, in setup and on the Remote tab. */
function SyncSecretsRow({
  form,
  onEdit,
  busy,
  secrets,
  confirmSecrets,
}: Pick<Props, "form" | "onEdit" | "busy" | "secrets" | "confirmSecrets">) {
  const { t } = useTranslation();
  return (
    <SettingsRow
      label={t("sync.remote.includeSecret")}
      labelFor="sync-with-secret"
      hint={t("sync.remote.includeSecretHint")}
      hintId="sync-with-secret-hint"
      wide={false}
      control={
        <SyncIncludeSecrets
          id="sync-with-secret"
          checked={form.includeSecret}
          confirm={confirmSecrets ?? false}
          secrets={secrets}
          url={form.url}
          disabled={busy}
          describedBy="sync-with-secret-hint"
          onChange={(includeSecret) => onEdit({ includeSecret }, true)}
        />
      }
    />
  );
}

/** The Remote tab's "Encrypted secrets" section. */
export function SyncSecretsSection(props: Props) {
  const { t } = useTranslation();
  return (
    <SettingsSection
      title={t("sync.remote.secretsSection.title")}
      description={t("sync.remote.secretsSection.hint")}
    >
      <SyncSecretsRow {...props} confirmSecrets />
    </SettingsSection>
  );
}

export function SyncRemoteFields(props: Props) {
  const { form, onEdit, errors, busy, setup = false } = props;
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
    <SettingsSection
      title={t("sync.remote.section.title")}
      description={t(setup ? "sync.remote.section.setup" : "sync.remote.section.saves")}
      testId="sync-remote-section"
    >
      <SettingsRow
        label={t("sync.remote.url")}
        labelFor="sync-url"
        hintId="sync-url-hint"
        hint={
          errors.url ? (
            <span className="text-danger" role="alert">
              {t(`sync.remote.errors.${errors.url}`)}
            </span>
          ) : (
            t("sync.setup.urlHint")
          )
        }
        control={
          <Input
            id="sync-url"
            className="w-full font-mono"
            placeholder="git@github.com:you/coffer-vault.git"
            aria-invalid={errors.url ? true : undefined}
            {...text("url")}
          />
        }
      />
      <SettingsRow
        label={t("sync.remote.branch")}
        labelFor="sync-branch"
        control={<Input id="sync-branch" className="w-full font-mono" {...text("branch")} />}
      />
      <SettingsRow
        label={t("sync.remote.secret")}
        labelFor="sync-secret"
        hintId="sync-secret-hint"
        hint={t("sync.setup.secretHint")}
        control={
          <SyncSecretPicker
            value={form.secretRef}
            disabled={busy}
            autoOpen={props.focusSecret}
            describedBy="sync-secret-hint"
            onChange={(secretRef) => onEdit({ secretRef }, true)}
          />
        }
      />
      {isHttpsUrl(form.url) ? (
        <SettingsRow
          label={t("sync.remote.username")}
          labelFor="sync-username"
          hintId="sync-username-hint"
          hint={t("sync.remote.usernameHint")}
          control={
            <Input
              id="sync-username"
              className="w-full"
              placeholder="coffer"
              aria-describedby="sync-username-hint"
              {...text("username")}
            />
          }
        />
      ) : null}
      <SettingsRow
        label={t("sync.remote.cadence.label")}
        labelFor="sync-cadence"
        hint={t("sync.setup.cadenceHint")}
        control={
          <SyncRoundCadence
            id="sync-cadence"
            intervalSeconds={form.intervalSeconds}
            enabled={form.enabled}
            disabled={busy}
            onChange={(next) => onEdit(next, true)}
          />
        }
      />
      {setup ? <SyncSecretsRow {...props} /> : null}
    </SettingsSection>
  );
}
