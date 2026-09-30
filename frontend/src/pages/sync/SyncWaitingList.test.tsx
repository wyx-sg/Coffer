// frontend/src/pages/sync/SyncWaitingList.test.tsx
//
// What waits to push is listed per file, with who wrote it in the four words a
// person reads the daemon's writers as.
import { describe, expect, test } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { formatDateTime } from "@/lib/utils";
import { SyncWaitingList } from "./SyncWaitingList";

const TIME = "2026-09-13T08:00:00Z";

function commit(writer: string, path: string, status: "added" | "modified" | "removed") {
  return { version: `v-${writer}`, time: TIME, writer, summary: "", changes: [{ path, status }] };
}

describe("SyncWaitingList", () => {
  test("lists each file with its change, writer and time", () => {
    render(
      <SyncWaitingList
        waiting={[
          commit("user", "knowledge/a.md", "added"),
          commit("curation", "knowledge/b.md", "modified"),
          commit("disk", "skills/x/SKILL.md", "removed"),
          commit("agent", "knowledge/c.md", "modified"),
        ]}
      />,
    );
    const rows = within(screen.getByTestId("sync-waiting")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent("knowledge/a.md");
    expect(rows[0]).toHaveTextContent(/added/i);
    expect(rows[0]).toHaveTextContent("You");
    expect(rows[0]).toHaveTextContent(formatDateTime(TIME));
    expect(rows[1]).toHaveTextContent("Coffer");
    expect(rows[2]).toHaveTextContent(/edited on disk/i);
    expect(rows[2]).toHaveTextContent(/removed/i);
    expect(rows[3]).toHaveTextContent("Agent");
  });

  test("nothing waiting renders nothing", () => {
    const { container } = render(<SyncWaitingList waiting={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
