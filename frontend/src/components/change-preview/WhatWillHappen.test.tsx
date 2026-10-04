// src/components/change-preview/WhatWillHappen.test.tsx
// The agent badge must keep its tile width beside a wrapping sentence.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { WhatWillHappen } from "./WhatWillHappen";

describe("WhatWillHappen", () => {
  test("the badge does not shrink under its sentence", () => {
    render(
      <WhatWillHappen
        summaries={[
          { agentType: "claude_code", agentName: "Claude Code", text: "Will add a skill." },
        ]}
      />,
    );
    const badge = screen.getAllByRole("img")[0];
    expect(badge.className).toContain("shrink-0");
    expect(badge.parentElement?.className).toContain("items-start");
  });
});
