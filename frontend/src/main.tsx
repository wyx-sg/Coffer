import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { credentialDesktopHost } from "./lib/tauri";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

/**
 * Credential the page on the desktop host, without holding up the paint.
 *
 * In a browser there is nothing to do: whoever served this document already
 * put the running daemon's token on `window.__COFFER_TOKEN__` (see lib/auth.ts).
 * The shell loads the bundle as a local asset, so no server touched the
 * document and the connection has to come over IPC instead.
 *
 * It deliberately does NOT block the first render. The handshake is fast only
 * when a daemon is already up; on a cold start it spawns one and waits, and
 * awaiting that before rendering would make every launch-after-reboot open on
 * an empty window for most of it — exactly the first impression a desktop app
 * cannot afford, and the opposite of what hosting the UI locally is for.
 * Rendering first means the shell shows the real application immediately, with
 * the offline banner explaining the gap, and the banner clears itself the
 * moment a connection lands. `credentialDesktopHost` keeps trying until one
 * does (see lib/tauri.ts); the promise it returns settles only on success, so
 * it is deliberately not awaited here.
 *
 * Every query fired before then answers `DAEMON_NOT_READY`, which the banner
 * renders as "still starting". Invalidating on success is therefore not an
 * optimisation but the repair: without it those queries keep that answer until
 * something else refetches them.
 */
function bootstrap(): void {
  void credentialDesktopHost(() => queryClient.invalidateQueries());
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
