// src/components/clis/AddCliDialog.tsx — Add a command-line tool by hand (no skill needed), or edit one added that way.
//
// The command is a name (`jq`) or the absolute path of an executable. While it
// is typed the dialog asks the daemon what it finds — where, which version, and
// whether the tool is already added or a skill already requires it — so the
// person sees what Coffer found before saving. A tool that is not on this
// machine can still be added (it shows as not found). Title, description,
// minimum version and a login check (a command line starting with the tool)
// are optional. Editing keeps the command fixed. Failures render inline.
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { useAddCli, useCliPreview, useEditCli } from "@/lib/hooks/useClis";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The tool being edited; omit to add a new one. */
  existing?: Cli;
  /** Called with the command once it is saved. */
  onSaved?: (command: string) => void;
}

/** What the lookup of the typed command found, in a line. */
function Found({ command }: { command: string }) {
  const { t } = useTranslation();
  const { data, isPending } = useCliPreview(command);
  if (isPending) return <p className="text-xs text-text-muted">{t("clis.add.looking")}</p>;
  if (!data) return null;
  if (data.added)
    return (
      <p className="text-xs text-danger">{t("clis.add.alreadyAdded", { command: data.command })}</p>
    );
  return (
    <div className="space-y-0.5 text-xs" data-testid="cli-found">
      {data.path ? (
        <p className="text-text-muted">
          {t("clis.add.foundAt")} <span className="font-mono text-text">{data.path}</span>
          {data.version ? (
            <>
              {" "}
              · <span className="font-mono text-text">{data.version}</span>
            </>
          ) : null}
        </p>
      ) : (
        <p className="text-warning">{t("clis.add.notFound", { command: data.command })}</p>
      )}
      {data.required ? <p className="text-text-muted">{t("clis.add.alsoRequired")}</p> : null}
    </div>
  );
}

function Form({ onOpenChange, existing, onSaved }: Omit<Props, "open">) {
  const { t } = useTranslation();
  const editing = existing !== undefined;
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
    if (editing) edit.mutate(fields, { onSuccess: done });
    else add.mutate({ command: command.trim(), ...fields }, { onSuccess: done });
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <DialogHeader>
        <DialogTitle>{t(editing ? "clis.add.editTitle" : "clis.add.title")}</DialogTitle>
        <DialogDescription>{t(editing ? "clis.add.editBody" : "clis.add.body")}</DialogDescription>
      </DialogHeader>
      <div className="space-y-1.5">
        <Label htmlFor="cli-command" required>
          {t("clis.add.command")}
        </Label>
        <Input
          id="cli-command"
          value={command}
          disabled={editing}
          autoFocus={!editing}
          placeholder={t("clis.add.commandPlaceholder")}
          className="font-mono"
          onChange={(e) => setCommand(e.target.value)}
        />
        {!editing && looked !== "" ? <Found command={looked} /> : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="cli-title">{t("clis.add.titleField")}</Label>
          <Input id="cli-title" value={title} onChange={(e) => setTitle(e.target.value)} />
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
        <Textarea
          id="cli-description"
          rows={2}
          value={description}
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
        <p className="text-2xs text-text-muted">{t("clis.add.loginCheckHint")}</p>
      </div>
      {save.error ? (
        <Alert variant="error">
          <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
        </Alert>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={!valid || save.isPending}>
          {t(editing ? "common.save" : "clis.add.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function AddCliDialog({ open, onOpenChange, existing, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[520px]">
        {open ? <Form onOpenChange={onOpenChange} existing={existing} onSaved={onSaved} /> : null}
      </DialogContent>
    </Dialog>
  );
}
