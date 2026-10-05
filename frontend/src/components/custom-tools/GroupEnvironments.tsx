// src/components/custom-tools/GroupEnvironments.tsx — a group's environments (CtGroupBody, on every group board): one row per environment with
// its switch, base URL, the state of its secrets and its variables; Edit…, Delete and Add environment. Every caller
// names the environment it calls (spec mcp-gateway "Choose a custom tool's environment on every call"), so a row
// is never "current": the same tools are sent to whichever one a call names.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";

import { Section } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import {
  useDeleteCustomToolEnvironment,
  useToggleCustomToolEnvironment,
} from "@/lib/hooks/useCustomToolEnvironments";
import { EnvironmentDialog } from "./EnvironmentDialog";

interface Props {
  group: CustomToolGroup;
}

const STATE_VARIANT = {
  present: "success",
  missing: "destructive",
  pending_approval: "warning",
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
      <ul className="flex flex-col divide-y divide-border-subtle rounded-lg border border-border-subtle">
        {envs.map((env) => (
          <li
            key={env.name}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5"
            data-testid={`environment-${env.name}`}
          >
            <Switch
              checked={env.enabled}
              aria-label={t("customTools.environments.switch", { name: env.name })}
              disabled={toggle.isPending}
              onCheckedChange={(enabled) => toggle.mutate({ name: env.name, enabled })}
            />
            <span className="font-mono text-sm font-medium">{env.name}</span>
            <span
              className="min-w-0 flex-1 truncate font-mono text-xs text-text-muted"
              title={env.base_url}
            >
              {env.base_url}
            </span>
            {env.secret_state !== "none" ? (
              <Badge variant={STATE_VARIANT[env.secret_state]}>
                <KeyRound className="size-3" aria-hidden />
                {t(`customTools.environments.secret.${env.secret_state}`)}
              </Badge>
            ) : null}
            {Object.keys(env.variables).length > 0 ? (
              <span className="font-mono text-xs text-text-muted">
                {Object.entries(env.variables)
                  .map(([k, v]) => `${k}=${v}`)
                  .join(" · ")}
              </span>
            ) : null}
            <span className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.environments.edit", { name: env.name })}
                onClick={() => setEditing(env)}
              >
                <Pencil aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.environments.delete", { name: env.name })}
                disabled={envs.length === 1}
                onClick={() => setDeleting(env)}
              >
                <Trash2 aria-hidden />
              </Button>
            </span>
          </li>
        ))}
      </ul>
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
