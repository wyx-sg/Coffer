import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { registerFrontendKinds } from "./kinds";
import { isTauri, getDaemonInfo } from "./lib/tauri";
import { setDaemonConnection } from "./lib/auth";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

// In the desktop app the daemon's port + token aren't known at build time, and
// the bundled frontend can't read ~/.coffer/daemon.json itself. Ask the Tauri
// shell (which detect-or-spawns the bundled daemon) and expose the result on
// `window` BEFORE the first render, so every API call carries the token. In a
// browser (dev / daemon-served) this is skipped — the token comes from the
// Vite env / localStorage as before. Failure is non-fatal: the app still
// mounts and shows its normal "service unreachable" state.
async function injectDaemonInfo(): Promise<void> {
  if (!isTauri()) return;
  try {
    const info = await getDaemonInfo();
    setDaemonConnection(info.baseUrl, info.token);
  } catch (e) {
    console.error("Coffer: could not get daemon info from the desktop shell", e);
  }
}

async function bootstrap(): Promise<void> {
  await injectDaemonInfo();
  registerFrontendKinds();
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
        {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

void bootstrap();
