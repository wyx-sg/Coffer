import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import { registerFrontendKinds } from "./kinds";
import { consumeSignInCode } from "./lib/webSession";
import "./i18n"; // Side-effect import; initialises i18next before render
import "./index.css";
import "highlight.js/styles/github.css"; // Code-block syntax theme (chat markdown)

async function bootstrap(): Promise<void> {
  // `coffer open` launches this page with a one-time code in the fragment.
  // Redeem it for the API token BEFORE the first render, so the very first
  // query already carries credentials. A missing or stale code is not an
  // error — the app falls through to the stored token, or renders its
  // unauthenticated state.
  await consumeSignInCode(window.location, (url) => window.history.replaceState(null, "", url));

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
