// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { GeneralSettings } from "./GeneralSettings";

afterEach(() => localStorage.clear());

describe("GeneralSettings", () => {
  test("renders the default page-size control reflecting the stored preference", () => {
    localStorage.setItem("coffer.pageSize", "50");
    render(<GeneralSettings />);
    expect(screen.getByText(/default rows per page/i)).toBeInTheDocument();
    // The Select trigger shows the persisted value.
    expect(screen.getByRole("combobox", { name: /default rows per page/i })).toHaveTextContent(
      "50",
    );
  });
});
