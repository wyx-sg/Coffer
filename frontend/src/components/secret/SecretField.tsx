// src/components/secret/SecretField.tsx — a field whose whole value is a secret
// (Foundations 0.2.05 · Secret field): provider API keys, channel / sync tokens,
// a tool group's auth. One 30px picker, "🔑 name ▾"; the value never shows.
//
// Empty, it takes a paste: the pasted text becomes a NEW secret named after the
// thing being configured (`defaultName`), kept in the form's state and written
// to Secrets when the form submits — call `persistNewSecrets([value])` from
// `@/components/secret/secretValue` then. A chosen name Coffer does not hold on this
// machine shows a "Missing" warning.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, KeyRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { fieldClass } from "@/components/ui/field-classes";
import { useSecretChoices } from "./useSecretChoices";
import { defaultSecretName, type SecretFieldValue } from "./secretValue";
import { cn } from "@/lib/utils";
import { SecretMenu } from "./SecretMenu";

interface Props {
  id?: string;
  value: SecretFieldValue;
  onChange: (value: SecretFieldValue) => void;
  /** Names the secret a paste creates ("openai" → "openai-key"): the thing being configured. */
  defaultName: string;
  disabled?: boolean;
  invalid?: boolean;
  "aria-label"?: string;
  /** The line under the field; false hides it. Defaults to "Kept in Coffer's Secrets…". */
  help?: string | false;
}

const SHELL = "flex h-control-md items-center gap-2 px-2.5 py-0 text-left";

function Picker({ id, value, onChange, defaultName, disabled, invalid, ...aria }: Props) {
  const { t } = useTranslation();
  const { names, loaded } = useSecretChoices();
  const input = useRef<HTMLInputElement>(null);
  const label = aria["aria-label"] ?? t("secretField.placeholder");
  const fresh = () => defaultSecretName(defaultName, names);
  const paste = (text: string) => {
    if (text !== "") onChange({ kind: "new", name: fresh(), value: text });
  };

  if (value === null) {
    return (
      <div
        className={cn(
          fieldClass,
          SHELL,
          "focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent-soft",
        )}
      >
        <KeyRound className="size-[13px] shrink-0 text-text-muted" aria-hidden />
        <input
          ref={input}
          id={id}
          value=""
          disabled={disabled}
          aria-label={label}
          aria-invalid={invalid}
          autoComplete="off"
          spellCheck={false}
          placeholder={t("secretField.placeholder")}
          onPaste={(e) => {
            e.preventDefault();
            paste(e.clipboardData.getData("text"));
          }}
          onChange={(e) => paste(e.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text-subtle"
        />
        <SecretMenu
          selected={null}
          disabled={disabled}
          defaultNewName={fresh()}
          onSelectStored={(name) => onChange({ kind: "stored", name })}
        >
          <button
            type="button"
            aria-label={t("secretField.pick", { label })}
            className="inline-flex text-text-subtle"
          >
            <ChevronDown className="size-[13px]" aria-hidden />
          </button>
        </SecretMenu>
      </div>
    );
  }

  const missing = value.kind === "stored" && loaded && !names.has(value.name);
  return (
    <SecretMenu
      selected={value.name}
      disabled={disabled}
      defaultNewName={fresh()}
      onSelectStored={(name) => onChange({ kind: "stored", name })}
      pendingName={
        value.kind === "new"
          ? { value: value.name, onChange: (name) => onChange({ ...value, name }) }
          : undefined
      }
    >
      <button
        id={id}
        type="button"
        disabled={disabled}
        aria-label={t("secretField.chosen", { label, name: value.name })}
        aria-invalid={invalid}
        className={cn(fieldClass, SHELL)}
      >
        <KeyRound className="size-[13px] shrink-0 text-text-muted" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{value.name}</span>
        {value.kind === "new" ? (
          <Badge variant="secondary" className="shrink-0 font-sans">
            {t("secretField.newBadge")}
          </Badge>
        ) : null}
        {missing ? (
          <Badge variant="warning" className="shrink-0 font-sans">
            {t("secretField.missing")}
          </Badge>
        ) : null}
        <ChevronDown className="size-[13px] shrink-0 text-text-subtle" aria-hidden />
      </button>
    </SecretMenu>
  );
}

export function SecretField({ help, ...props }: Props) {
  const { t } = useTranslation();
  const text = help === undefined ? t("secretField.hint") : help;
  return (
    <div className="flex flex-col gap-1.5">
      <Picker {...props} />
      {text ? <p className="text-xs text-text-muted">{text}</p> : null}
    </div>
  );
}
