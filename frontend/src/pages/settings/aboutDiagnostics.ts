// src/pages/settings/aboutDiagnostics.ts — the plain-text lines Settings › About's "Copy diagnostics" puts on the clipboard.
//
// Spec web-ui "Keep daemon shutdown on the command line": version, release
// channel, host, daemon state and port, and the enabled experimental features —
// never a token or a secret. Built only from the status probe's public fields
// and the host, so nothing credential-shaped can reach it.
import type { components } from "@/lib/api/types";
import type { DaemonFooterState } from "@/components/shell/useDaemonFooterState";

type DaemonStatus = components["schemas"]["DaemonStatusOut"];

interface Input {
  status: DaemonStatus | undefined;
  state: DaemonFooterState;
  /** "desktop app" or "browser", already worded. */
  host: string;
  platform: string;
}

/** The diagnostics block, one `Label: value` line each. */
export function diagnosticsText({ status, state, host, platform }: Input): string {
  const features = status
    ? Object.entries(status.features)
        .filter(([, on]) => on)
        .map(([name]) => name)
        .sort()
    : [];
  const daemon = state.kind === "running" ? `running on port ${state.port}` : state.kind;
  const lines = [
    `Coffer: ${status?.version ?? "unknown"}`,
    `Channel: ${status?.channel ?? "unknown"}`,
    `Host: ${host}${platform ? ` (${platform})` : ""}`,
    `Daemon: ${daemon}`,
    `Features: ${features.length > 0 ? features.join(", ") : "none"}`,
  ];
  return lines.join("\n");
}
