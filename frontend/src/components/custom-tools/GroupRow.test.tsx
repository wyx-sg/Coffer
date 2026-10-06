// src/components/custom-tools/GroupRow.test.tsx — a group's row says where it points: one environment's host, or
// how many environments a group has (no one environment stands for the group).
import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { CustomToolGroup } from "@/lib/api/customTools";
import { GroupRow } from "./GroupRow";
import { makeGroup } from "./testFixtures";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: undefined }) }));
vi.mock("@/lib/api/secret", () => ({ secretsApi: { list: vi.fn(async () => ({ refs: [] })) } }));

function row(group: CustomToolGroup) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ul>
          <GroupRow
            group={group}
            selected={false}
            onOpen={vi.fn()}
            checked={false}
            onCheckedChange={vi.fn()}
          />
        </ul>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("a group with one environment names its host", () => {
  row(makeGroup());
  expect(screen.getByText("billing.internal.example · 1 tool")).toBeVisible();
});

test("a group with several environments counts them instead of naming the first one's host", () => {
  const base = makeGroup();
  const [first] = base.environments;
  row({
    ...base,
    environments: [
      first,
      { ...first, name: "uat", base_url: "https://uat.example" },
      { ...first, name: "live", base_url: "https://live.example" },
    ],
  });
  expect(screen.getByText("3 environments · 1 tool")).toBeVisible();
  expect(screen.queryByText(/billing\.internal\.example/)).toBeNull();
});
