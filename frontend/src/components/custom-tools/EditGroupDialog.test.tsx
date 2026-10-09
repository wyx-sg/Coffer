// src/components/custom-tools/EditGroupDialog.test.tsx — Edit group (640): the description and timeout only — base
// URLs, headers and secrets are the environments' — and no reach field.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { customToolsApi } from "@/lib/api/customTools";
import { secretsApi } from "@/lib/api/secret";
import { acceptance } from "@/test/acceptance";
import { EditGroupDialog } from "./EditGroupDialog";
import { makeGroup } from "./testFixtures";

vi.mock("@/lib/api/customTools", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/customTools")>()),
  customToolsApi: { update: vi.fn(), get: vi.fn(), list: vi.fn() },
}));
const TOKEN_ID = vi.hoisted(() => "c3".repeat(16));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: `secret/${TOKEN_ID}`,
          label: "billing-token",
          present: true,
          locked: false,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
    set: vi.fn(async () => ({ approval: null })),
    setNotes: vi.fn(async () => ({})),
  },
}));

const update = customToolsApi.update as unknown as ReturnType<typeof vi.fn>;
const group = makeGroup({
  headers: [
    {
      name: "Authorization",
      value: null,
      scheme: "Bearer",
      secret: TOKEN_ID,
      secret_state: "present",
    },
  ],
});

function open(onOpenChange = vi.fn()) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <EditGroupDialog group={group} open onOpenChange={onOpenChange} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return screen.getByRole("dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  update.mockResolvedValue(group);
});

describe("EditGroupDialog", () => {
  test("is 640 wide, Cancel is ghost, and there is no Available to field", () => {
    const dialog = open();
    expect(dialog.className).toContain("max-w-[640px]");
    expect(within(dialog).queryByText("Available to")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" }).className).toContain(
      "bg-transparent",
    );
  });

  acceptance("web-ui", "Edit group edits only the description and timeout", async () => {
    const onOpenChange = vi.fn();
    const dialog = open(onOpenChange);
    expect(within(dialog).queryByLabelText(/Base URL/)).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "Add header" })).toBeNull();
    expect(within(dialog).getByText(/belong to the environments/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Timeout"), { target: { value: "45" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("billing", {
        description: group.description,
        timeout_seconds: 45,
      }),
    );
    expect(secretsApi.set).not.toHaveBeenCalled();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
