// src/components/settings/daemon/DaemonPortRow.tsx — the editable port of the daemon's next start (design 6.2.11).
//
// Spec web-ui "Show and manage the daemon on Settings → Daemon" and daemon
// "Bind a fixed, settable port": a whole number from 1024 to 65535 that no
// other program holds, each refused in place (the daemon checks it and names
// the holder); saving writes it for the next start, and the row then says it
// takes effect after Coffer restarts, with Restart now — the shell's restart
// in the desktop shell, the daemon's own in a browser, which then reloads the
// page from the new port. The status above keeps showing the port the daemon
// answers on until then.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { restartErrorText } from "@/lib/daemonRestart";
import { useRestartDaemon } from "@/lib/hooks/useDaemon";
import { useDaemonPort, useSetDaemonPort } from "@/lib/hooks/useDaemonPort";

const MIN_PORT = 1024;
const MAX_PORT = 65535;

interface Holder {
  pid?: number;
  name?: string;
}

interface Props {
  /** The daemon cannot be reached: the field is shown but cannot change. */
  disabled: boolean;
}

export function DaemonPortRow({ disabled }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const port = useDaemonPort(!disabled);
  const save = useSetDaemonPort();
  const restart = useRestartDaemon();
  const [value, setValue] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (port.data) setValue(String(port.data.port));
  }, [port.data]);

  const refusal = (): string | null => {
    if (localError) return localError;
    const err = save.error;
    if (!err) return null;
    if (err instanceof ApiError && err.code === "PORT_IN_USE") {
      const details = (err.details ?? {}) as { port?: number; holder?: Holder | null };
      const holder = details.holder;
      return holder?.name
        ? t("settings.daemonTab.portInUseBy", {
            port: details.port,
            name: holder.name,
            pid: holder.pid,
          })
        : t("settings.daemonTab.portInUse", { port: details.port });
    }
    if (err instanceof ApiError && err.code === "PORT_OUT_OF_RANGE") {
      return t("settings.daemonTab.portRange", { min: MIN_PORT, max: MAX_PORT });
    }
    return translateApiError(t, err);
  };

  const submit = () => {
    save.reset();
    const n = Number(value.trim());
    if (!Number.isInteger(n) || n < MIN_PORT || n > MAX_PORT) {
      setLocalError(t("settings.daemonTab.portRange", { min: MIN_PORT, max: MAX_PORT }));
      return;
    }
    setLocalError(null);
    save.mutate(n);
  };

  const error = refusal();
  const pending = port.data?.pending ? port.data.port : null;
  const unchanged = port.data !== undefined && value.trim() === String(port.data.port);

  return (
    <>
      <SettingRow
        label={t("settings.daemonTab.port")}
        labelFor={id}
        description={t("settings.daemonTab.portHelp", { min: MIN_PORT, max: MAX_PORT })}
        status={
          error ? (
            <span className="text-xs text-danger" role="alert">
              {error}
            </span>
          ) : null
        }
      >
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Input
            id={id}
            inputMode="numeric"
            className="w-24 font-mono"
            value={value}
            disabled={disabled || port.data === undefined || save.isPending}
            aria-invalid={error ? true : undefined}
            onChange={(e) => {
              setValue(e.target.value);
              setLocalError(null);
              save.reset();
            }}
          />
          <Button
            type="submit"
            variant="outline"
            disabled={disabled || unchanged || save.isPending || value.trim() === ""}
          >
            {t("settings.daemonTab.save")}
          </Button>
        </form>
      </SettingRow>
      {pending !== null ? (
        <div
          className="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3"
          data-testid="settings-daemon-port-pending"
          role="status"
        >
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm font-medium text-text">
                {t("settings.daemonTab.portPending", { port: pending })}
              </span>
              <span className="text-xs text-text-muted">
                {t("settings.daemonTab.portPendingHelp")}
              </span>
            </div>
            <Button onClick={() => restart.mutate()} disabled={restart.isPending}>
              {restart.isPending
                ? t("daemon.offline.restarting")
                : t("settings.daemonTab.restartNow")}
            </Button>
          </div>
          {restart.error ? (
            <p className="text-xs text-danger" role="alert">
              {restartErrorText(t, restart.error)}
            </p>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
