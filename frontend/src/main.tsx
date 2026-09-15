import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { connectToShellDaemon, isTauri } from "./lib/tauri";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

/**
 * Credential the page on the desktop host, without holding up the paint.
 *
 * In a browser there is nothing to do: whoever served this document already
 * put the running daemon's token on `window.__COFFER_TOKEN__` (see lib/auth.ts).
 * The shell loads the bundle as a local asset, so no server touched the
 * document and the token has to come over IPC instead.
 *
 * It deliberately does NOT block the first render. `get_daemon_info` is fast
 * only when a daemon is already up; on a cold start it spawns one and polls
 * for as long as fifteen seconds, and awaiting that before rendering would
 * make every launch-after-reboot open on an empty window for most of it —
 * exactly the first impression a desktop app cannot afford, and the opposite
 * of what hosting the UI locally is for. Rendering first means the shell shows
 * the real application immediately, with the offline banner explaining the
 * gap, and the banner clears itself the moment this resolves.
 *
 * Every query fired before it resolves goes out unauthenticated and comes back
 * `UNAUTHENTICATED`, which the banner already renders as "daemon not ready".
 * Invalidating on success is therefore not an optimisation but the repair:
 * without it those queries keep their 401 until something else refetches them.
 */
function credentialDesktopHost(): void {
  if (!isTauri()) return;
  connectToShellDaemon()
    .then(() => queryClient.invalidateQueries())
    .catch((e: unknown) => {
      // Non-fatal by design. The invoke rejects when the shell could not find
      // or start a daemon at all, and the right answer is the app sitting
      // there with its offline banner — the surface that explains the problem
      // and offers the restart. A blank window explains nothing.
      console.error("Coffer: could not get daemon info from the desktop shell", e);
    });
}

function bootstrap(): void {
  credentialDesktopHost();
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
        {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

bootstrap();
