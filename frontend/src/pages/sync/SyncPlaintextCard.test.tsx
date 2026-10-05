// frontend/src/pages/sync/SyncPlaintextCard.test.tsx
//
// A round that found a plaintext secret: the card names each place (never a
// value), opens the Secrets page's move scoped to the flagged files, carries
// no agent hand-off, and pushes anyway only after the confirmation.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { PlaintextContext } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncProblemBanner } from "./SyncProblemBanner";
import { syncState, primaryAction } from "./syncPageState";
import { idleMutation, makeRound, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({
  usePushAnyway: vi.fn(),
  usePlaintextContext: vi.fn(),
}));
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: () => <button>Hand off to Claude Code</button>,
}));
vi.mock("@/components/secret/ScanSecretsDialog", () => ({
  ScanSecretsDialog: ({ open, only }: { open: boolean; only?: readonly string[] }) =>
    open ? (
      <div role="dialog" aria-label="Find plaintext keys">
        {(only ?? []).join(" ")}
      </div>
    ) : null,
}));
vi.mock("./useSyncIgnore", async (orig) => ({
  ...(await orig<typeof import("./useSyncIgnore")>()),
  useSyncIgnore: () => ({ isIgnored: () => false, ignorer: () => undefined }),
}));

const { usePushAnyway, usePlaintextContext } = await import("@/lib/hooks/useSync");

const MASK = "•".repeat(16);
const CONTEXT: PlaintextContext = {
  path: "knowledge/team/db.md",
  line: 4,
  key: "DB_PASSWORD",
  rule: "generic-api-key",
  change: "modified",
  on_remote: false,
  lines: [
    { number: 3, text: "Host: db.internal", values: [] },
    {
      number: 4,
      text: `DB_PASSWORD=${MASK}`,
      values: [
        {
          start: 12,
          end: 28,
          key: "DB_PASSWORD",
          rule: "generic-api-key",
          shape: {
            length: 16,
            classes: ["lower", "digit"],
            prefix: null,
            hint: "placeholder",
            word: "example",
          },
        },
      ],
    },
  ],
  diff: `--- remote/x\n+++ local/x\n@@ -1,1 +1,2 @@\n Host: db.internal\n+DB_PASSWORD=${MASK}\n`,
  added: 1,
  removed: 0,
};

const STATUS = makeStatus({
  last_round: makeRound({ status: "plaintext_found" }),
  problem: {
    kind: "plaintext_found",
    message: "a plaintext secret in knowledge/team/db.md; nothing was pushed",
    secret_ref: null,
    since: null,
    handoff: null,
    plaintext: [
      { path: "knowledge/team/db.md", line: 4, key: "DB_PASSWORD", current: true, rule: "generic-api-key" },
      { path: "resources/mcp/x.json", line: 7, key: "token", current: true, rule: "stripe-access-token" },
      { path: "knowledge/old.md", line: 2, key: "API_KEY", current: false, rule: "generic-api-key" },
    ],
  },
});

function renderCard(mutate = vi.fn()) {
  vi.mocked(usePushAnyway).mockReturnValue(
    idleMutation({ mutate }) as unknown as ReturnType<typeof usePushAnyway>,
  );
  vi.mocked(usePlaintextContext).mockImplementation(
    (_path, _line, enabled) =>
      ({
        data: enabled ? CONTEXT : undefined,
        isLoading: false,
        error: null,
      }) as unknown as ReturnType<typeof usePlaintextContext>,
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
    "the Sync page names each place and offers Move into secrets and push anyway",
    () => {
      const { mutate, card } = renderCard();
      expect(card).toHaveTextContent("Nothing was pushed: 2 files hold a plaintext secret");
      const places = within(card).getByTestId("sync-plaintext-places");
      expect(places).toHaveTextContent("knowledge/team/db.md, line 4");
      expect(places).toHaveTextContent("the value of DB_PASSWORD");
      expect(places).toHaveTextContent("a value shaped like a token");
      expect(places).toHaveTextContent("stripe-access-token");
      // A value only in an unpushed commit is folded away by the round, not listed.
      expect(places).not.toHaveTextContent("knowledge/old.md");
      expect(within(card).queryByRole("button", { name: /retry/i })).toBeNull();

      // A secret is never handed to an agent: the card moves it into secrets itself.
      expect(within(card).queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
      expect(within(card).queryByRole("button", { name: /copy prompt/i })).toBeNull();
      fireEvent.click(within(card).getByRole("button", { name: "Move into secrets…" }));
      const move = screen.getByRole("dialog", { name: "Find plaintext keys" });
      expect(move).toHaveTextContent("knowledge/team/db.md resources/mcp/x.json");
      expect(move).not.toHaveTextContent("knowledge/old.md");

      fireEvent.click(within(card).getByRole("button", { name: "Push anyway…" }));
      expect(mutate).not.toHaveBeenCalled();
      const dialog = screen.getByRole("dialog", { name: "Push these files anyway?" });
      expect(dialog).toHaveTextContent("records that you did in the audit log");
      fireEvent.click(within(dialog).getByRole("button", { name: "I checked it, push anyway" }));
      expect(mutate).toHaveBeenCalledTimes(1);
    },
  );

  acceptance("vault-sync", "the Sync page opens each place to its masked lines", () => {
    const { card } = renderCard();
    expect(within(card).queryByTestId("sync-plaintext-context")).toBeNull();
    fireEvent.click(
      within(card).getByRole("button", { name: "Show knowledge/team/db.md, line 4 in its file" }),
    );
    const context = within(card).getByTestId("sync-plaintext-context");
    expect(context).toHaveTextContent("Changed file");
    expect(context).toHaveTextContent("Host: db.internal");
    const flagged = context.querySelector("[data-flagged]");
    expect(flagged).toHaveTextContent(`DB_PASSWORD=${MASK}`);
    expect(flagged?.querySelector("mark")).toHaveTextContent(MASK);
    expect(context).toHaveTextContent("16 characters: lowercase, digits");
    expect(within(context).getByTestId("sync-plaintext-rule")).toHaveTextContent("generic-api-key");
    expect(context).toHaveTextContent("contains “example”, often an example or placeholder");

    expect(within(card).queryByTestId("sync-plaintext-diff")).toBeNull();
    fireEvent.click(within(context).getByRole("button", { name: "Show changes" }));
    expect(within(card).getByTestId("sync-plaintext-diff")).toHaveTextContent(
      `DB_PASSWORD=${MASK}`,
    );
  });

  test("the page reads it as its own state, with Sync now as the round action", () => {
    const state = syncState(STATUS);
    expect(state).toMatchObject({ kind: "plaintext_found", tone: "err" });
    expect(primaryAction(state.kind)).toEqual({ syncing: false, disabled: false });
  });
});
