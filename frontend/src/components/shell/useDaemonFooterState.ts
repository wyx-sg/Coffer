// src/components/shell/useDaemonFooterState.ts — the daemon state the sidebar footer names.
//
// Four states in plain words (spec web-ui "Show the daemon's state in the
// shell footer"): connecting before the first answer, running (with its port),
// stopping while the daemon reports `draining`, and offline when it cannot be
// reached. It reads the one status poll the offline banner already reads — no
// second timer — and checks the error first, so the footer never reads
// running while the banner is up, even over a stale cached answer.
import { useDaemonOutOfDate, useDaemonStatus } from "@/lib/hooks/useDaemon";

export type DaemonFooterState =
  | { kind: "connecting" }
  | { kind: "running"; port: number; outOfDate: boolean; version: string }
  | { kind: "stopping" }
  | { kind: "offline" };

export function useDaemonFooterState(): DaemonFooterState {
  const status = useDaemonStatus();
  // Desktop only: a daemon an earlier app version left running still answers,
  // so it reads as running, with a version warning (secret-supplier
  // module, `lib/tauri.ts`; a browser answers "matches").
  const outOfDate = useDaemonOutOfDate(status.data?.version).data === true;
  if (status.isError) return { kind: "offline" };
  if (!status.data) return { kind: "connecting" };
  if (status.data.status === "draining") return { kind: "stopping" };
  return { kind: "running", port: status.data.port, outOfDate, version: status.data.version };
}
