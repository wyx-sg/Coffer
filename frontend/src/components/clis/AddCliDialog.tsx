// src/components/clis/AddCliDialog.tsx — Add a command-line tool by hand (no skill needed), or edit any listed one.
//
// The command is a name (`jq`) or the absolute path of an executable. While it
// is typed the dialog asks the daemon what it finds — where, which version, and
// whether the tool is already added or a skill already requires it — so the
// person sees what Coffer found before saving. A tool that is not on this
// machine can still be added (it shows as not found). A display name (the
// wire's `title`), description, minimum version and a login check (a command
// line starting with the tool) are optional. Editing shows the command locked
// and every field. For a tool only a skill or MCP server requires, the fields
// open on what the skills say and only the ones changed are sent: they become
// the person's edits, and a cleared one brings the skills' value back (spec
// skill-manager "Declare a command-line tool without a skill"). A failed save
// stays in the dialog and the primary button becomes Retry.
import { CircleAlert, Lock } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { useAddCli, useEditCli } from "@/lib/hooks/useClis";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { CliFound } from "./CliFound";

/** The daemon's limit (domain/skill/cli_declared.py DESCRIPTION_MAX). */
const DESCRIPTION_MAX = 1000;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The tool being edited; omit to add a new one. */
  existing?: Cli;
  /** Called with the command once it is saved. */
  onSaved?: (command: string) => void;
}

function Form({ onOpenChange, existing, onSaved }: Omit<Props, "open">) {
  const { t } = useTranslation();
  const editing = existing !== undefined;
  /** A tool a skill or MCP server requires and nobody added: what is saved is the person's edits. */
  const required = editing && !existing.added;
  const add = useAddCli();
  const edit = useEditCli(existing?.command ?? "");
  const save = editing ? edit : add;
  const [command, setCommand] = useState(existing?.command ?? "");
  const [title, setTitle] = useState(existing?.title ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [minVersion, setMinVersion] = useState(existing?.min_version ?? "");
  const [loginCheck, setLoginCheck] = useState(existing?.login.check?.join(" ") ?? "");
  const looked = useDebouncedValue(command.trim(), 400);
  const valid = command.trim() !== "";

  const submit = () => {
    if (!valid || save.isPending) return;
    const fields = {
      title: title.trim() || null,
      description: description.trim() || null,
      min_version: minVersion.trim() || null,
      login_check: loginCheck.trim() || null,
    };
    const done = (cli: Cli) => {
      onOpenChange(false);
      onSaved?.(cli.command);
    };
    if (required) edit.mutate(changedFrom(existing, fields), { onSuccess: done });
    else if (editing) edit.mutate(fields, { onSuccess: done });
    else add.mutate({ command: command.trim(), ...fields }, { onSuccess: done });
  };

  const command_ = existing?.command ?? command.trim();
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {editing ? t("clis.add.editTitle", { command: existing.command }) : t("clis.add.title")}
        </DialogTitle>
        <DialogDescription>
          {t(required ? "clis.add.requiredBody" : editing ? "clis.add.editBody" : "clis.add.body")}
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-1.5">
        <Label htmlFor="cli-command" required={!editing}>
          {t("clis.add.command")}
        </Label>
        {editing ? (
          <>
            <div className="relative">
              <Input
                id="cli-command"
                value={existing.command}
                disabled
                className="bg-surface-sunken pr-8 font-mono"
              />
              <Lock
                className="absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-text-subtle"
                aria-hidden
              />
            </div>
            <p className="text-xs text-text-muted">{t("clis.add.fixed")}</p>
          </>
        ) : (
          <>
            <Input
              id="cli-command"
              value={command}
              autoFocus
              placeholder={t("clis.add.commandPlaceholder")}
              className="font-mono"
              onChange={(e) => setCommand(e.target.value)}
            />
            {looked !== "" ? <CliFound command={looked} /> : null}
          </>
        )}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_140px] gap-2.5">
        <div className="space-y-1.5">
          <Label htmlFor="cli-title">{t("clis.add.titleField")}</Label>
          <Input
            id="cli-title"
            value={title}
            autoComplete="off"
            placeholder={t("clis.add.titlePlaceholder")}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cli-min">{t("clis.add.minVersion")}</Label>
          <Input
            id="cli-min"
            value={minVersion}
            placeholder="2.40"
            className="font-mono"
            onChange={(e) => setMinVersion(e.target.value)}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="cli-description">{t("clis.add.description")}</Label>
        <Input
          id="cli-description"
          value={description}
          maxLength={DESCRIPTION_MAX}
          autoComplete="off"
          autoFocus={editing}
          placeholder={t("clis.add.descriptionPlaceholder")}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="cli-login">{t("clis.add.loginCheck")}</Label>
        <Input
          id="cli-login"
          value={loginCheck}
          placeholder="gh auth status"
          className="font-mono"
          onChange={(e) => setLoginCheck(e.target.value)}
        />
        <p className="text-xs text-text-muted">{t("clis.add.loginCheckHint")}</p>
      </div>
      {save.error ? (
        <Alert variant="error">
          <CircleAlert aria-hidden />
          <AlertTitle>
            {t(editing ? "clis.add.editFailed" : "clis.add.addFailed", { command: command_ })}
          </AlertTitle>
          <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
        </Alert>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={!valid || save.isPending}>
          {save.error ? t("common.retry") : t(editing ? "common.save" : "clis.add.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

type Fields = {
  title: string | null;
  description: string | null;
  min_version: string | null;
  login_check: string | null;
};

/** Only the fields that differ from what the tool reads now. */
function changedFrom(cli: Cli, fields: Fields): Partial<Fields> {
  const now: Fields = {
    title: cli.title ?? null,
    description: cli.description ?? null,
    min_version: cli.min_version ?? null,
    login_check: cli.login.check?.join(" ") ?? null,
  };
  return Object.fromEntries(
    (Object.keys(fields) as (keyof Fields)[])
      .filter((k) => fields[k] !== now[k])
      .map((k) => [k, fields[k]]),
  );
}

export function AddCliDialog({ open, onOpenChange, existing, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[480px]">
        {open ? <Form onOpenChange={onOpenChange} existing={existing} onSaved={onSaved} /> : null}
      </DialogContent>
    </Dialog>
  );
}
