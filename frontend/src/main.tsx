import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { registerFrontendKinds } from "./kinds";
import { connectToShellDaemon, isTauri } from "./lib/tauri";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

async function bootstrap(): Promise<void> {
  // Credential the page, if this host needs it. In a browser there is nothing
  // to do: whoever served this document already put the running daemon's token
  // on `window.__COFFER_TOKEN__` (see lib/auth.ts). The desktop shell loads the
  // bundle as a local asset, so no server touched the document — ask the shell
  // over IPC and write the same globals, before the first render, so the very
  // first query carries credentials either way.
  if (isTauri()) {
    try {
      await connectToShellDaemon();
    } catch (e) {
      // Deliberately non-fatal. The invoke rejects when the shell could not
      // find or start a daemon, and the right answer to that is the app
      // rendering with its offline banner — the surface that explains the
      // problem and offers the restart. A blank window explains nothing.
      console.error("Coffer: could not get daemon info from the desktop shell", e);
    }
  }

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
