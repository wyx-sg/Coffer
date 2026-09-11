import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { registerFrontendKinds } from "./kinds";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

function bootstrap(): void {
  // No credential step: whoever served this document already put the running
  // daemon's token on `window.__COFFER_TOKEN__` (see lib/auth.ts), so the very
  // first query carries credentials.
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

bootstrap();
