// src/components/mcp/server/McpRequires.test.tsx — a Requires secret row shows the env var, the secret's
// readable name linking to its page, and Replace key… (only when the parent can rebind).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { McpRequires } from "./McpRequires";

const ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OTHER = "secret/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const row = (ref: string, label: string) => ({
  ref,
  label,
  present: true,
  cited_by: [],
  mentioned_by_skills: [],
  bindings: [],
});

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    set: vi.fn(async () => undefined),
    list: vi.fn(async () => ({
      refs: [row(`secret/${ID}`, "Sentry token"), row(OTHER, "Team key")],
    })),
  },
}));

const REQUIRES = [
  { kind: "secret", name: "SENTRY_TOKEN", status: "set", version: null, secret: ID },
] as const;

function renderRequires(onRebind?: (r: unknown, ref: string) => Promise<unknown>) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <MemoryRouter>
          <McpRequires requires={REQUIRES} onRebind={onRebind} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("McpRequires", () => {
  test("a secret row names the env var and links the secret by its readable name", async () => {
    renderRequires(vi.fn());
    expect(screen.getByText("SENTRY_TOKEN")).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: "Sentry token" });
    expect(link).toHaveAttribute("href", `/secrets/${encodeURIComponent(`secret/${ID}`)}`);
    expect(screen.queryByText(ID)).toBeNull();
  });

  test("without a rebind handler there is no Replace key button", async () => {
    renderRequires();
    await screen.findByRole("link", { name: "Sentry token" });
    expect(screen.queryByRole("button", { name: /replace key/i })).toBeNull();
  });

  test("Replace key… with another secret hands the env var and ref to the parent", async () => {
    const onRebind = vi.fn(async () => undefined);
    renderRequires(onRebind);
    fireEvent.click(await screen.findByRole("button", { name: /replace key/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Use another secret" }));
    fireEvent.click(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: /team key/i }));
    fireEvent.click(screen.getByRole("button", { name: "Use this secret" }));
    await waitFor(() => expect(onRebind).toHaveBeenCalled());
    expect(onRebind).toHaveBeenCalledWith(expect.objectContaining({ name: "SENTRY_TOKEN" }), OTHER);
  });
});
