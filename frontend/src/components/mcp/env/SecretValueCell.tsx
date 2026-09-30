// src/components/mcp/env/SecretValueCell.tsx — the value half of a Secret row
// when stored secrets can be picked (boards Mcp-Edit / Mcp-EditStdio).
//
// A row either cites a stored secret — its own (named by its key, with Stored
// or Missing and a Replace button) or one from the Secrets page — or holds a
// value typed for a new secret. "New value…" swaps the picker for the typed
// value; "Use stored" goes back. Replace types a value that is written through
// the row's own ref (a blank value keeps the stored one).
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from "@/components/ui/select";
import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";
import { isOwnRef, pickerRefs, refLabel } from "./secretRefs";

/** Radix Select has no free-text item; "type a new value" is this sentinel. */
const NEW_VALUE = "__new__";

interface Props {
  row: ParsedEnvVar;
  /** Names on the Secrets page (present ones). */
  secretNames: readonly string[];
  /** Refs known to hold a value; undefined while the list is loading. */
  present: ReadonlySet<string> | undefined;
  label: string;
  autoFocus: boolean;
  onChange: (patch: Partial<ParsedEnvVar>) => void;
  /** Replace was pressed: the typed value input should take focus. */
  onReplace: () => void;
}

export function SecretValueCell({
  row,
  secretNames,
  present,
  label,
  autoFocus,
  onChange,
  onReplace,
}: Props) {
  const { t } = useTranslation();
  const key = row.key || label;
  const refs = pickerRefs(row, secretNames);
  const ref = row.ref ?? null;

  if (ref === null) {
    const keeps = !!row.storedRef && row.key.trim() === row.loadedKey;
    return (
      <>
        <PasswordInput
          aria-label={t("mcp.env.newValueOf", { key })}
          containerClassName="min-w-0 flex-[1.3]"
          autoFocus={autoFocus}
          value={row.value}
          placeholder={keeps ? t("common.secretKeepBlank") : t("mcp.add.secretValue")}
          onChange={(e) => onChange({ value: e.target.value })}
        />
        {refs.length > 0 ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => onChange({ ref: row.storedRef ?? refs[0], value: "" })}
          >
            {t("mcp.env.useStored")}
          </Button>
        ) : null}
      </>
    );
  }

  const own = isOwnRef(row, ref);
  const missing = present !== undefined && !present.has(ref);
  return (
    <>
      <Select
        value={ref}
        onValueChange={(next) =>
          onChange(next === NEW_VALUE ? { ref: null, value: "" } : { ref: next, value: "" })
        }
      >
        <SelectTrigger
          aria-label={t("mcp.env.storedSecretFor", { key })}
          className="min-w-0 flex-[1.3] font-mono"
        >
          <span className="flex min-w-0 items-center gap-2">
            {own ? <KeyRound className="size-3.5 shrink-0 text-text-subtle" aria-hidden /> : null}
            <span className="truncate">{refLabel(ref)}</span>
            {missing ? (
              <Badge variant="destructive" className="ml-auto shrink-0 font-sans">
                {t("mcp.env.missing")}
              </Badge>
            ) : own && present !== undefined ? (
              <Badge variant="success" className="ml-auto shrink-0 font-sans">
                {t("mcp.edit.stored")}
              </Badge>
            ) : null}
          </span>
        </SelectTrigger>
        <SelectContent>
          {refs.map((r) => (
            <SelectItem key={r} value={r} className="font-mono">
              {refLabel(r)}
            </SelectItem>
          ))}
          <SelectSeparator />
          <SelectItem value={NEW_VALUE}>{t("mcp.env.newValue")}</SelectItem>
        </SelectContent>
      </Select>
      {own ? (
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onChange({ ref: null, value: "" });
            onReplace();
          }}
        >
          {t("mcp.edit.replace")}
        </Button>
      ) : null}
    </>
  );
}
