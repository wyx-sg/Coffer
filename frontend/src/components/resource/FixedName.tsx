// src/components/resource/FixedName.tsx
// How a kind whose name is fixed (MCP server, skill) shows that name: a badge
// beside the detail header, and a read-only field in the edit form with a note
// saying why it cannot change. Neither offers a control that edits it — the
// daemon refuses a rename of these kinds (409 NAME_IMMUTABLE).
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

/** Beside the detail header: the name is fixed. */
export function FixedNameBadge() {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
      <Lock className="size-3" aria-hidden />
      {t("resources.fixedName.badge")}
    </Badge>
  );
}

interface FieldProps {
  id: string;
  name: string;
  /** Why this kind's name is fixed — what agents use it for. */
  hint: string;
}

/** In the edit form: the name, read-only, with the note. */
export function FixedNameField({ id, name, hint }: FieldProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5" role="group" aria-labelledby={`${id}-label`}>
      <p id={`${id}-label`} className="text-sm font-medium leading-none">
        {t("resources.fixedName.label")}
      </p>
      <p className="flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 font-mono text-sm">
        <Lock className="size-3.5 text-muted-foreground" aria-hidden />
        {name}
      </p>
      <p className="text-xs text-muted-foreground">
        {hint} {t("resources.fixedName.cannotChange")}
      </p>
    </div>
  );
}
