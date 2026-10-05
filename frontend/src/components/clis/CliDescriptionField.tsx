// src/components/clis/CliDescriptionField.tsx — a command's description, edited in place in its header.
//
// Any command takes one, whether the person added it or a skill or MCP server
// requires it (spec skill-manager "Declare a command-line tool without a
// skill"). Leaving the field or pressing Enter saves; an empty value clears it.
// A failure is shown under the field.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { useEditCli } from "@/lib/hooks/useClis";

/** The daemon's limit (domain/skill/cli_declared.py DESCRIPTION_MAX). */
const DESCRIPTION_MAX = 1000;

export function CliDescriptionField({ cli }: { cli: Cli }) {
  const { t } = useTranslation();
  const edit = useEditCli(cli.command);
  const errorId = useId();
  const saved = cli.description ?? "";
  const [draft, setDraft] = useState(saved);
  useEffect(() => setDraft(saved), [saved, cli.command]);

  const save = () => {
    const next = draft.trim();
    if (next === saved || edit.isPending) return;
    edit.mutate({ description: next || null });
  };
  return (
    <div className="min-w-0">
      <Input
        value={draft}
        aria-label={t("clis.detail.description")}
        aria-describedby={edit.error ? errorId : undefined}
        maxLength={DESCRIPTION_MAX}
        autoComplete="off"
        placeholder={t("clis.detail.descriptionPlaceholder")}
        className="-ml-1.5 h-auto border-transparent bg-transparent px-1.5 text-xs text-text-muted shadow-none hover:border-border focus-visible:bg-surface"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          }
        }}
      />
      {edit.error ? (
        <p id={errorId} role="alert" className="pt-1 text-xs text-danger">
          {translateApiError(t, edit.error)}
        </p>
      ) : null}
    </div>
  );
}
