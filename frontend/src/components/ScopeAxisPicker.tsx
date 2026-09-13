// frontend/src/components/ScopeAxisPicker.tsx
//
// One axis of a resource's activation scope (ADR per-agent-resource-scope):
// "everything" or an explicit selection. Agents and machines are the same
// control with different rows, so they are one component and not two.
//
// Machines are why this is a PICK-LIST and never a text field: `scope` names a
// machine by its derived id, and a mistyped id matches nothing, which silently
// makes the resource dormant instead of failing (spec vault-sync
// `### Scope gains a machine axis`). Names already in the list that this vault
// does not recognise still render — a resource can legally be scoped to an
// agent or a machine that has not appeared here yet — badged as unknown rather
// than dropped, which would rewrite the user's scope behind their back.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";

export interface AxisOption {
  /** What `scope` stores: an agent name, or a machine's derived id. */
  id: string;
  label: string;
  /** A second line under the label — the id behind a machine's display name. */
  detail?: string;
  /** Rendered with a "this machine" marker. */
  isLocal?: boolean;
}

interface Props {
  titleKey: string;
  everyKey: string;
  emptyKey: string;
  unknownKey: string;
  options: AxisOption[];
  /** `null` = unrestricted. */
  value: string[] | null;
  onChange: (next: string[] | null) => void;
  disabled: boolean;
  testIdPrefix: string;
}

export function ScopeAxisPicker({
  titleKey,
  everyKey,
  emptyKey,
  unknownKey,
  options,
  value,
  onChange,
  disabled,
  testIdPrefix,
}: Props) {
  const { t } = useTranslation();
  const selected = value ?? [];
  const known = options.map((option) => option.id);
  const rows: AxisOption[] = [
    ...options,
    ...selected.filter((id) => !known.includes(id)).map((id) => ({ id, label: id })),
  ];

  const toggle = (id: string, checked: boolean) => {
    const base = value ?? [];
    onChange(checked ? [...base, id] : base.filter((entry) => entry !== id));
  };

  return (
    <div className="space-y-2" data-testid={`${testIdPrefix}-axis`}>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t(titleKey)}
      </p>

      <label className="flex w-full cursor-pointer items-center gap-2 text-sm">
        <Checkbox
          checked={value === null}
          disabled={disabled}
          aria-label={t(everyKey)}
          onChange={(e) => onChange(e.target.checked ? null : [])}
        />
        <span>{t(everyKey)}</span>
      </label>

      {value === null ? null : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t(emptyKey)}</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((row) => (
            <label
              key={row.id}
              data-testid={`${testIdPrefix}-${row.id}`}
              className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2 text-sm"
            >
              <Checkbox
                checked={selected.includes(row.id)}
                disabled={disabled}
                aria-label={row.label}
                onChange={(e) => toggle(row.id, e.target.checked)}
              />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{row.label}</span>
                {row.detail ? (
                  <span className="ml-2 font-mono text-xs text-muted-foreground">{row.detail}</span>
                ) : null}
              </span>
              {row.isLocal ? <Badge variant="secondary">{t("scope.thisMachine")}</Badge> : null}
              {known.includes(row.id) ? null : <Badge variant="outline">{t(unknownKey)}</Badge>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
