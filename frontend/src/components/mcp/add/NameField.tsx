// frontend/src/components/mcp/add/NameField.tsx — the Name field of a new MCP
// server, shared by the one-server form and every review card.
//
// The value is normalised as it is typed (lower case, other characters to
// hyphens) so what is shown is what will be registered; it is fixed once added,
// so the problems the daemon would refuse it for are said under the field.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { nameProblem } from "./nameProblem";

interface Props {
  id: string;
  value: string;
  onChange: (name: string) => void;
  /** Names another server already has. */
  taken: ReadonlySet<string>;
  /** The help line under the field; the form's names the tool prefix. */
  help?: string;
  /** Hide the visible label (a review card shows the name as its heading). */
  compact?: boolean;
}

/** What the name box keeps of a keystroke: the daemon's characters, lower
 *  case, spaces turned into hyphens. Not trimmed of a trailing hyphen while
 *  typing, or `my-` could never become `my-server`. */
function typedName(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9_.-]+/g, "-");
}

export function NameField({ id, value, onChange, taken, help, compact = false }: Props) {
  const { t } = useTranslation();
  const problem = nameProblem(value, taken);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} required className={compact ? "sr-only" : undefined}>
        {t("mcp.add.name")}
      </Label>
      <Input
        id={id}
        value={value}
        className="font-mono"
        spellCheck={false}
        aria-invalid={problem ? true : undefined}
        onChange={(e) => onChange(typedName(e.target.value))}
      />
      {problem ? (
        <p className="text-xs text-danger" role="alert">
          {t(`mcp.add.${problem.key}`, problem.params)}
        </p>
      ) : help ? (
        <p className="text-xs text-text-muted">{help}</p>
      ) : null}
    </div>
  );
}
