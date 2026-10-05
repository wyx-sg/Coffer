// src/components/secret/SecretNameLink.test.tsx — a secret a resource uses is shown by name and links to its page.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { SecretName, SecretNameLink } from "./SecretNameLink";

const REF = "secret/b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2";

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2",
          label: "Acme key",
          present: true,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));

function wrap(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SecretNameLink", () => {
  test("shows the label and links to the secret's own page", async () => {
    wrap(<SecretNameLink secretRef={REF} />);
    const link = await screen.findByRole("link", { name: "Acme key" });
    expect(link).toHaveAttribute("href", `/secrets/${encodeURIComponent(REF)}`);
    expect(document.body).not.toHaveTextContent("8b7a01dd");
  });

  test("a ref the list does not hold reads as Unnamed secret, never its id", async () => {
    wrap(<SecretNameLink secretRef="secret/00000000000000000000000000000000" />);
    expect(await screen.findByRole("link", { name: "Unnamed secret" })).toBeInTheDocument();
  });

  test("SecretName is the same name as plain text", async () => {
    wrap(<SecretName secretRef={REF} />);
    expect(await screen.findByText("Acme key")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
