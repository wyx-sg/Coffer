// frontend/src/pages/settings/AboutPage.tsx
//
// Settings → About (design 6.2.13): what this Coffer is. A head line with the
// running version and release channel and, beside it, "Copy diagnostics for a
// bug report" (spec web-ui "Keep daemon shutdown on the command line": version,
// channel, host, daemon state and port and the enabled features, never a token
// or a secret); the desktop shell's update check (`UpdatesSection`, its own
// requirement); and the details — version, license and source. The version
// comes from /daemon/status so it names the build that is actually running.
import { useTranslation } from "react-i18next";

import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { useDaemonFooterState } from "@/components/shell/useDaemonFooterState";
import { useToast } from "@/components/ui/toast";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { isTauri } from "@/lib/tauri";
import { diagnosticsText } from "./aboutDiagnostics";
import { UpdatesSection } from "./UpdatesSection";

const SOURCE_URL = "https://github.com/wyx-sg/Coffer";
const EMPTY = "—";

export function AboutPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: status } = useDaemonStatus();
  const state = useDaemonFooterState();

  const copyDiagnostics = async () => {
    const text = diagnosticsText({
      status,
      state,
      host: isTauri() ? "desktop app" : "browser",
      platform: typeof navigator !== "undefined" ? navigator.platform : "",
    });
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("settings.about.diagnosticsCopied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const version = status?.version ?? EMPTY;
  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-col gap-1" data-testid="settings-about-head">
        <h3 className="m-0 text-lg font-bold text-text">Coffer</h3>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-text-muted">
          <span>
            {status
              ? t("settings.about.versionLine", { version, channel: status.channel })
              : t("settings.about.versionLineLoading")}
          </span>
          <button
            type="button"
            onClick={() => void copyDiagnostics()}
            className="text-sm text-accent underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {t("settings.about.copyDiagnostics")}
          </button>
        </p>
      </div>

      <UpdatesSection />

      <SettingsSection title={t("settings.about.details")}>
        <SettingRow label={t("settings.about.fields.version")}>
          <span className="font-mono text-xs">{version}</span>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.license")}>
          <span className="text-sm">MIT</span>
        </SettingRow>
        <SettingRow label={t("settings.about.fields.source")}>
          <a
            href={SOURCE_URL}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-accent hover:underline"
          >
            github.com/wyx-sg/Coffer
          </a>
        </SettingRow>
      </SettingsSection>
    </div>
  );
}
