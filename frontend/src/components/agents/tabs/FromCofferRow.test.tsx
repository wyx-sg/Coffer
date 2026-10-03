// src/components/agents/tabs/FromCofferRow.test.tsx — "From Coffer": a count, the first five names, "+N more", a link.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Sparkle } from "lucide-react";

import "@/i18n";
import { FromCofferRow } from "./FromCofferRow";

function renderRow(names: string[]) {
  return render(
    <MemoryRouter>
      <FromCofferRow
        icon={Sparkle}
        description="Coffer installs these into Claude Code."
        title={`${names.length} skills from Coffer`}
        names={names}
        linkLabel="Open Skills"
        to="/skills?agent=u-cc"
      />
    </MemoryRouter>,
  );
}

describe("FromCofferRow", () => {
  test("spells the first five names and counts the rest", () => {
    renderRow(["a", "b", "c", "d", "e", "f", "g"]);
    expect(screen.getByRole("heading", { name: "From Coffer" })).toBeInTheDocument();
    expect(screen.getByText("a · b · c · d · e · +2 more")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Skills/ })).toHaveAttribute(
      "href",
      "/skills?agent=u-cc",
    );
  });

  test("five or fewer names have no +N more", () => {
    renderRow(["a", "b"]);
    expect(screen.getByText("a · b")).toBeInTheDocument();
  });

  test("with none, only the headline and the link remain", () => {
    renderRow([]);
    expect(screen.getByText("0 skills from Coffer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Skills/ })).toBeInTheDocument();
  });
});
