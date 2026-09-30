import { test, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

test("App renders the shell with the sidebar nav by default", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>,
  );
  // The Layout's sidebar Coffer link is always present
  expect(await screen.findByText("Coffer")).toBeInTheDocument();
  // The sidebar exposes the MCP servers nav link as the canonical
  // entry point — assert on its role rather than a loose text match
  // (the heading and the link both render "MCP servers", and so does the
  // Overview's Health tile at `/`, hence the scope to the sidebar).
  const nav = await screen.findByRole("navigation", { name: "Primary navigation" });
  expect(await within(nav).findByRole("link", { name: /MCP servers/i })).toBeInTheDocument();
});
