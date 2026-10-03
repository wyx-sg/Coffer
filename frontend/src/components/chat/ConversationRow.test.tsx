// src/components/chat/ConversationRow.test.tsx — the status a list row shows.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Conversation } from "@/lib/api/chat";
import { acceptance } from "@/test/acceptance";
import { ConversationRow } from "./ConversationRow";

const conv = (over: Partial<Conversation>): Conversation => ({
  id: "c1",
  agent_key: "claude_code",
  title: "Fix reconnect",
  archived_at: null,
  channel_binding: null,
  created_at: "2026-10-03T08:00:00Z",
  updated_at: "2026-10-03T08:00:00Z",
  preview: null,
  running: false,
  needs_you: false,
  ...over,
});

function renderRow(c: Conversation) {
  return render(
    <MemoryRouter>
      <ul>
        <ConversationRow
          conversation={c}
          href={`/conversations/${c.id}`}
          agentName="Claude Code"
          selected={false}
          selecting={false}
          archivedView={false}
          now={new Date("2026-10-03T12:00:00Z")}
          onToggle={() => undefined}
          onArchive={() => undefined}
          onDelete={() => undefined}
        />
      </ul>
    </MemoryRouter>,
  );
}

describe("ConversationRow status", () => {
  acceptance("chat", "a waiting conversation is marked and counted", () => {
    renderRow(conv({ running: true, needs_you: true }));
    // Waiting on the owner outranks Running.
    expect(screen.getByText("Needs you")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });

  test("a running conversation that waits on nothing says Running", () => {
    renderRow(conv({ running: true }));
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.queryByText("Needs you")).not.toBeInTheDocument();
  });
});
