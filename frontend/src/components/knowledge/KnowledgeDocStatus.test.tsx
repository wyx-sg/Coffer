// frontend/src/components/knowledge/KnowledgeDocStatus.test.tsx
//
// The per-document embed-status badge mapper. Asserts it renders a badge with
// the localized label for each known status, and nothing for an unknown/absent
// status (labels from knowledge.detail.embedStatus.*).
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { DocEmbedStatus } from "./KnowledgeDocStatus";

describe("DocEmbedStatus", () => {
  test.each([
    ["done", "Embedded"],
    ["embedding", "Embedding"],
    ["queued", "Queued"],
    ["running", "Embedding"],
    ["error", "Embed failed"],
  ])("renders a badge for status %s", (status, label) => {
    render(<DocEmbedStatus status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  test("renders nothing for an unknown status", () => {
    const { container } = render(<DocEmbedStatus status="bogus" />);
    expect(container).toBeEmptyDOMElement();
  });

  test("renders nothing when status is absent (null / undefined)", () => {
    const { container } = render(<DocEmbedStatus status={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
