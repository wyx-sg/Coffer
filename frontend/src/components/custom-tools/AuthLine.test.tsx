// src/components/custom-tools/AuthLine.test.tsx — a header's secret reads by its name, never its id.
import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { headersWithSecret } from "./headerRows";
import { AuthLine } from "./AuthLine";

const ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: `secret/${ID}`,
          label: "Deploy token",
          present: true,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));

function renderLine(plain: boolean) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthLine header="Authorization" secret={ID} plain={plain} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("shows the readable name as a link to the secret", async () => {
  renderLine(false);
  const link = await screen.findByRole("link", { name: "Deploy token" });
  expect(link).toHaveAttribute("href", `/secrets/${encodeURIComponent(`secret/${ID}`)}`);
  expect(screen.queryByText(ID)).toBeNull();
});

test("inside a form it is plain text", async () => {
  renderLine(true);
  expect(await screen.findByText("Deploy token")).toBeInTheDocument();
  expect(screen.queryByRole("link")).toBeNull();
});

test("headersWithSecret changes only the named header", () => {
  const group = {
    headers: [
      { name: "Authorization", secret: ID },
      { name: "X-Org", value: "acme" },
      { name: "X-Key", secret: "other" },
    ],
  } as never;
  expect(headersWithSecret(group, "Authorization", "new")).toEqual([
    { name: "Authorization", secret: "new" },
    { name: "X-Org", value: "acme" },
    { name: "X-Key", secret: "other" },
  ]);
});
