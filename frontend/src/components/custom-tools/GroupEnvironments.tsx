// src/components/custom-tools/GroupEnvironments.tsx — a group's Environments tab: one card per environment, everything
// it holds readable without opening it — its switch, name and secret state with Edit and ⋯ (Delete) in the card's
// head; then its base URL, its timeout and whose it is, its headers in the shared table (a secret by its name and
// state) and its variables. Add environment sits above the cards. Every caller names the environment it calls (spec
// mcp-gateway "Choose a custom tool's environment on every call"), so a card is never "current": the same tools
// are sent to whichever one a call names.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Pencil, Plus } from "lucide-react";

import { Section } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ActionMenu } from "@/components/ui/menu";
import { Switch } from "@/components/ui/switch";
import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import { effectiveTimeout } from "@/lib/customTools/environmentContext";
import {
  useDeleteCustomToolEnvironment,
  useToggleCustomToolEnvironment,
} from "@/lib/hooks/useCustomToolEnvironments";
import { cn } from "@/lib/utils";
import { EnvironmentDialog } from "./EnvironmentDialog";
import { HeaderTable } from "./HeaderTable";

interface Props {
  group: CustomToolGroup;
}

const STATE_VARIANT = {
  present: "success",
  missing: "destructive",
  pending_approval: "warning",
  rejected: "destructive",
  none: "default",
} as const;

export function GroupEnvironments({ group }: Props) {
  const { t } = useTranslation();
  const toggle = useToggleCustomToolEnvironment(group.name);
  const del = useDeleteCustomToolEnvironment(group.name);
  const [editing, setEditing] = useState<CustomToolEnvironment | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<CustomToolEnvironment | null>(null);
  const envs = group.environments ?? [];

  return (
    <Section
      title={t("customTools.environments.title")}
      help={t("customTools.environments.help")}
      as="h2"
      gap="tight"
      labelled
      actions={
        <Button variant="outline" size="sm" onClick={() => setEditing(null)}>
          <Plus aria-hidden />
          {t("customTools.environments.add")}
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        {envs.map((env) => (
          <EnvironmentCard
            key={env.name}
            group={group}
            env={env}
            toggling={toggle.isPending}
            onToggle={(enabled) => toggle.mutate({ name: env.name, enabled })}
            onEdit={() => setEditing(env)}
            onDelete={envs.length > 1 ? () => setDeleting(env) : null}
          />
        ))}
      </div>
      <EnvironmentDialog
        group={group}
        environment={editing ?? null}
        open={editing !== undefined}
        onOpenChange={(open) => !open && setEditing(undefined)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
            del.reset();
          }
        }}
        title={t("customTools.environments.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("customTools.environments.deleteBody", { group: group.name })}
        confirmLabel={t("customTools.environments.deleteConfirm")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDelete", { name: deleting?.name ?? "" })}
        pending={del.isPending}
        error={del.error}
        onConfirm={() => {
          if (deleting) del.mutate(deleting.name, { onSuccess: () => setDeleting(null) });
        }}
      />
    </Section>
  );
}

interface CardProps {
  group: CustomToolGroup;
  env: CustomToolEnvironment;
  toggling: boolean;
  onToggle: (enabled: boolean) => void;
  onEdit: () => void;
  /** null: the group's last environment, which cannot be deleted. */
  onDelete: (() => void) | null;
}

function EnvironmentCard({ group, env, toggling, onToggle, onEdit, onDelete }: CardProps) {
  const { t } = useTranslation();
  const timeout = effectiveTimeout(group, env);
  const variables = Object.entries(env.variables ?? {});
  return (
    <article
      aria-label={env.name}
      data-testid={`environment-${env.name}`}
      className={cn(
        "overflow-hidden rounded-lg border border-border-subtle",
        !env.enabled && "opacity-70",
      )}
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-border-subtle bg-surface-sunken px-4 py-2.5">
        <Switch
          checked={env.enabled}
          aria-label={t("customTools.environments.switch", { name: env.name })}
          disabled={toggling}
          onCheckedChange={onToggle}
        />
        <span className="font-mono text-sm font-semibold">{env.name}</span>
        {!env.enabled ? (
          <Badge variant="secondary">{t("customTools.environments.off")}</Badge>
        ) : null}
        {env.secret_state !== "none" ? (
          <Badge variant={STATE_VARIANT[env.secret_state]}>
            <KeyRound className="size-3" aria-hidden />
            {t(`customTools.environments.secret.${env.secret_state}`)}
          </Badge>
        ) : null}
        <span className="ml-auto flex shrink-0 items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            aria-label={t("customTools.environments.edit", { name: env.name })}
            onClick={onEdit}
          >
            <Pencil aria-hidden />
            {t("common.edit")}
          </Button>
          <ActionMenu
            label={t("customTools.environments.more", { name: env.name })}
            actions={[
              {
                key: "delete",
                label: t("customTools.environments.deleteConfirm"),
                description: onDelete ? undefined : t("customTools.environments.lastOne"),
                destructive: true,
                disabled: onDelete === null,
                onSelect: () => onDelete?.(),
              },
            ]}
          />
        </span>
      </header>
      <div className="flex flex-col gap-4 px-4 py-3.5">
        {env.description ? <p className="text-sm text-text-muted">{env.description}</p> : null}
        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
          <Fact label={t("customTools.fields.baseUrl")}>
            <span className="break-all font-mono text-xs">{env.base_url}</span>
          </Fact>
          <Fact label={t("customTools.editGroup.timeout")}>
            {t(`customTools.environments.timeout.${timeout.source}`, { seconds: timeout.seconds })}
          </Fact>
        </dl>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-label text-text-muted">
            {t("customTools.fields.headers")}
          </span>
          <HeaderTable
            ariaLabel={t("customTools.environments.headersOf", { name: env.name })}
            empty={t("customTools.editor.noHeaders")}
            rows={env.headers.map((h) => ({
              name: h.name,
              value: h.value,
              secret: h.secret,
              secretState: h.secret_state,
            }))}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-label text-text-muted">
            {t("customTools.environments.variables")}
          </span>
          <HeaderTable
            ariaLabel={t("customTools.environments.variablesOf", { name: env.name })}
            empty={t("customTools.environments.noVariables")}
            rows={variables.map(([name, value]) => ({ name: `{env:${name}}`, value }))}
          />
        </div>
      </div>
    </article>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}
