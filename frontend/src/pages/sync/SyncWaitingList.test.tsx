// frontend/src/pages/sync/SyncWaitingList.test.tsx
//
// What waits to push is one line per file (6.5.02): its change mark and path,
// then who wrote it — in the four words a person reads the daemon's writers
// as — and when.
import { describe, expect, test } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SyncWaitingList } from "./SyncWaitingList";
import { clock } from "./syncTime";

const TIME = "2026-09-13T08:00:00Z";

function commit(writer: string, path: string, status: "added" | "modified" | "removed") {
  return { version: `v-${writer}`, time: TIME, writer, summary: "", changes: [{ path, status }] };
}

describe("SyncWaitingList", () => {
  test("lists each file with its change mark, writer and time", () => {
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
    const lines = within(screen.getByTestId("sync-waiting")).getAllByRole("listitem");
    expect(lines).toHaveLength(4);
    expect(lines[0]).toHaveTextContent("+ knowledge/a.md");
    expect(lines[0]).toHaveTextContent(`You · ${clock(TIME)}`);
    expect(lines[1]).toHaveTextContent("~ knowledge/b.md");
    expect(lines[1]).toHaveTextContent("Coffer");
    expect(lines[2]).toHaveTextContent("− skills/x/SKILL.md");
    expect(lines[2]).toHaveTextContent(/edited on disk/i);
    expect(lines[3]).toHaveTextContent("Agent");
  });

  test("nothing waiting renders nothing", () => {
    const { container } = render(<SyncWaitingList waiting={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
