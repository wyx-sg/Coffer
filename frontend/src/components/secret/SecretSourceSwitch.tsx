// src/components/secret/SecretSourceSwitch.tsx — inside a replace dialog: a new value, or another stored secret.
//
// "New value" writes into the secret the resource already uses (every other
// user of that secret gets it too); "Use another secret" points this one
// resource at a different stored secret and leaves the old one untouched.
import { useTranslation } from "react-i18next";

import { Combobox } from "@/components/ui/combobox";
import { Segmented } from "@/components/ui/segmented";
import { SECRET_PREFIX } from "./secretRows";
import { useSecretChoices } from "./useSecretChoices";

export type SecretSource = "value" | "existing";

interface Props {
  source: SecretSource;
  onSourceChange: (source: SecretSource) => void;
  /** The ref the resource uses now — not offered as "another" secret. */
  currentRef: string;
  /** The picked ref (`secret/<id>`), or "" while none is picked. */
  picked: string;
  onPick: (ref: string) => void;
  disabled?: boolean;
}

export function SecretSourceSwitch({
  source,
  onSourceChange,
  currentRef,
  picked,
  onPick,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const { options } = useSecretChoices();
  const others = options.filter((o) => `${SECRET_PREFIX}${o.name}` !== currentRef);
  return (
    <div className="flex flex-col gap-3">
      <Segmented<SecretSource>
        label={t("secretRef.source")}
        value={source}
        disabled={disabled}
        onChange={onSourceChange}
        options={[
          { value: "value", label: t("secretRef.newValue") },
          { value: "existing", label: t("secretRef.useExisting") },
        ]}
      />
      {source === "existing" ? (
        <div className="flex flex-col gap-1.5">
          <Combobox
            id="secret-ref-pick"
            value={picked || null}
            options={others.map((o) => ({
              value: `${SECRET_PREFIX}${o.name}`,
              label: o.display,
              hint: o.usedBy ? t("secretField.usedBy", { count: o.usedBy }) : undefined,
            }))}
            onChange={onPick}
            placeholder={t("secretRef.pickPlaceholder")}
            emptyMessage={t("secretRef.pickEmpty")}
            disabled={disabled}
          />
          <p className="text-xs text-text-muted">{t("secretRef.existingHint")}</p>
        </div>
      ) : null}
    </div>
  );
}
