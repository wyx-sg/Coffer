// src/components/settings/daemon/useDaemonState.ts — the daemon state Settings (Daemon, About) names.
//
// Five states in plain words: connecting before the first answer, running (with
// its port and version), stopping while the daemon reports `draining`,
// reconnecting for the first seconds after it stops answering, and offline
// after that. It reads the one status poll the rest of the shell reads — no
// second timer — and the phase `useDaemonConnectionDriver` publishes, and
// checks the error first, so it never reads running while the shell says the
// daemon is gone, even over a stale cached answer.
import { useDaemonOutOfDate, useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useDaemonConnection } from "@/components/shell/daemonConnection";

export type DaemonState =
  | { kind: "connecting" }
  | { kind: "running"; port: number; version: string; outOfDate: boolean }
  | { kind: "stopping"; version: string | null }
  | { kind: "reconnecting"; version: string | null }
  | { kind: "offline"; version: string | null };

export function useDaemonState(): DaemonState {
  const status = useDaemonStatus();
  const connection = useDaemonConnection();
  // Desktop only: a daemon an earlier app version left running still answers,
  // so it reads as running, with a version warning (credential-supplier
  // module, `lib/tauri.ts`; a browser answers "matches").
  const outOfDate = useDaemonOutOfDate(status.data?.version).data === true;
  const version = status.data?.version ?? null;
  if (status.isError) {
    return connection.driven && connection.phase !== "offline"
      ? { kind: "reconnecting", version }
      : { kind: "offline", version };
  }
  if (!status.data) return { kind: "connecting" };
  if (status.data.status === "draining") return { kind: "stopping", version };
  return {
    kind: "running",
    port: status.data.port,
    version: status.data.version,
    outOfDate,
  };
}
