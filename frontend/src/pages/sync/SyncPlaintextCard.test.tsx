// frontend/src/pages/sync/SyncPlaintextCard.test.tsx
//
// A round that found a plaintext secret: the card names each place (never a
// value), carries the agent hand-off, and pushes anyway only after the
// confirmation.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { SyncProblemBanner } from "./SyncProblemBanner";
import { syncState, primaryAction } from "./syncPageState";
import { idleMutation, makeRound, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ usePushAnyway: vi.fn() }));
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: ({ prompt }: { prompt: string }) => <button title={prompt}>Ask an agent</button>,
}));
vi.mock("./useSyncIgnore", async (orig) => ({
  ...(await orig<typeof import("./useSyncIgnore")>()),
  useSyncIgnore: () => ({ isIgnored: () => false, ignorer: () => undefined }),
}));

const { usePushAnyway } = await import("@/lib/hooks/useSync");

const STATUS = makeStatus({
  last_round: makeRound({ status: "plaintext_found" }),
  problem: {
    kind: "plaintext_found",
    message: "a plaintext secret in knowledge/team/db.md; nothing was pushed",
    secret_ref: null,
    since: null,
    handoff: { prompt: "move each value into a Coffer secret" },
    plaintext: [
      { path: "knowledge/team/db.md", line: 4, key: "DB_PASSWORD", current: true },
      { path: "resources/mcp/x.json", line: 7, key: "token", current: true },
      { path: "knowledge/old.md", line: 2, key: "API_KEY", current: false },
    ],
  },
});

function renderCard(mutate = vi.fn()) {
  vi.mocked(usePushAnyway).mockReturnValue(
    idleMutation({ mutate }) as unknown as ReturnType<typeof usePushAnyway>,
  );
  render(
    <MemoryRouter>
      <SyncProblemBanner status={STATUS} runs={[]} onRecheck={vi.fn()} rechecking={false} />
    </MemoryRouter>,
  );
  return { mutate, card: screen.getByTestId("sync-problem") };
}

describe("SyncPlaintextCard", () => {
  acceptance(
    "vault-sync",
    "the Sync page names each place and offers the hand-off and push anyway",
    () => {
      const { mutate, card } = renderCard();
      expect(card).toHaveTextContent("Nothing was pushed: 2 files hold a plaintext secret");
      const places = within(card).getByTestId("sync-plaintext-places");
      expect(places).toHaveTextContent("knowledge/team/db.md, line 4");
      expect(places).toHaveTextContent("the value of DB_PASSWORD");
      expect(places).toHaveTextContent("a value shaped like a token");
      // A value only in an unpushed commit is folded away by the round, not listed.
      expect(places).not.toHaveTextContent("knowledge/old.md");
      expect(within(card).queryByRole("button", { name: /retry/i })).toBeNull();

      // The hand-off asks an agent to move the values; the card has no scan of its own.
      expect(within(card).getByRole("button", { name: "Ask an agent" })).toHaveAttribute(
        "title",
        "move each value into a Coffer secret",
      );
      expect(within(card).queryByRole("button", { name: "Move into secrets…" })).toBeNull();

      fireEvent.click(within(card).getByRole("button", { name: "Push anyway…" }));
      expect(mutate).not.toHaveBeenCalled();
      const dialog = screen.getByRole("dialog");
      expect(dialog).toHaveTextContent("records that you did in the audit log");
      fireEvent.click(within(dialog).getByRole("button", { name: "I checked it, push anyway" }));
      expect(mutate).toHaveBeenCalledTimes(1);
    },
  );

  test("the page reads it as its own state, with Sync now as the round action", () => {
    const state = syncState(STATUS);
    expect(state).toMatchObject({ kind: "plaintext_found", tone: "err" });
    expect(primaryAction(state.kind)).toEqual({ syncing: false, disabled: false });
  });
});
