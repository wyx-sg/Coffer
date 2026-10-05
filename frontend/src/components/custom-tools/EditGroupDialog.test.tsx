// src/components/custom-tools/EditGroupDialog.test.tsx — Edit group (640): the group's headers are the shared rows —
// a secret row sends {name, secret} (the whole value, no prefix), a plain row {name, value}; a typed-in new secret
// is written to Secrets before the group names it; there is no reach field.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { customToolsApi } from "@/lib/api/customTools";
import { secretsApi } from "@/lib/api/secret";
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
  headers: [{ name: "Authorization", value: null, secret: TOKEN_ID, secret_state: "present" }],
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
  test("is 640 wide, Cancel is ghost, and there is no Available to field", async () => {
    const dialog = open();
    expect(dialog.className).toContain("max-w-[640px]");
    expect(within(dialog).queryByText("Available to")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" }).className).toContain(
      "bg-transparent",
    );
    expect(
      await within(dialog).findByRole("button", { name: /Choose a secret|billing-token/ }),
    ).toBeTruthy();
  });

  test("saves secret rows by name and plain rows by value, sending the whole headers list", async () => {
    const onOpenChange = vi.fn();
    const dialog = open(onOpenChange);
    fireEvent.click(within(dialog).getByRole("button", { name: "Add header" }));
    fireEvent.change(within(dialog).getAllByLabelText("Headers name")[1], {
      target: { value: "X-Team" },
    });
    fireEvent.change(within(dialog).getByLabelText("Value of X-Team"), {
      target: { value: "core" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "billing",
        expect.objectContaining({
          headers: [
            { name: "Authorization", secret: TOKEN_ID },
            { name: "X-Team", value: "core" },
          ],
          timeout_seconds: 30,
        }),
      ),
    );
    expect(secretsApi.set).not.toHaveBeenCalled();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a pasted secret is written to Secrets before the group is saved", async () => {
    const dialog = open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add header" }));
    fireEvent.change(within(dialog).getAllByLabelText("Headers name")[1], {
      target: { value: "X-Api-Key" },
    });
    // Choosing "new" happens through the row's own "Store it in Coffer?" hint on a secret-looking value.
    fireEvent.change(within(dialog).getByLabelText("Value of X-Api-Key"), {
      target: { value: "k-9f8e7d6c5b4a3210" },
    });
    fireEvent.click(await within(dialog).findByRole("button", { name: /Store it in Coffer/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    // Stored under a minted id, labelled after the group and header; the header cites the id.
    const [ref, value] = vi.mocked(secretsApi.set).mock.calls[0];
    expect(ref).toMatch(/^secret\/[0-9a-f]{32}$/);
    expect(value).toBe("k-9f8e7d6c5b4a3210");
    expect(secretsApi.setNotes).toHaveBeenCalledWith(ref, { label: "billing-X-Api-Key" });
    const body = update.mock.calls[0][1] as { headers: unknown[] };
    expect(body.headers).toContainEqual({ name: "X-Api-Key", secret: ref.slice("secret/".length) });
  });
});
