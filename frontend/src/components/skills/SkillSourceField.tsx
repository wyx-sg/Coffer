// frontend/src/components/skills/SkillSourceField.tsx
// One mono text field of the Change source form, with its help or error line under it.
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SourceField({
  id,
  label,
  required,
  help,
  helpTone,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  required?: boolean;
  help?: string | null;
  helpTone?: "danger";
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} required={required}>
        {label}
      </Label>
      <Input
        id={id}
        className="font-mono text-xs"
        value={value}
        disabled={disabled}
        spellCheck={false}
        autoComplete="off"
        aria-invalid={helpTone === "danger" || undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {help ? (
        <p className={helpTone === "danger" ? "text-xs text-danger" : "text-xs text-text-muted"}>
          {help}
        </p>
      ) : null}
    </div>
  );
}
