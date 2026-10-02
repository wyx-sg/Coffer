// src/components/settings/SettingsLayout.test.tsx — SettingsSection is a labelled region; SettingRow ties its label and helper to the control.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingRow, SettingsSection } from "./SettingsLayout";

describe("SettingsSection", () => {
  it("is a region named by its heading, with the description and action in its header", () => {
    render(
      <SettingsSection title="Replies" description="How it answers" action={<button>Act</button>}>
        <SettingRow label="Row one">x</SettingRow>
      </SettingsSection>,
    );
    const region = screen.getByRole("region", { name: "Replies" });
    expect(within(region).getByRole("heading", { level: 3, name: "Replies" })).toBeInTheDocument();
    fireEvent.click(within(region).getByRole("button", { name: "More info" }));
    expect(screen.getByText("How it answers")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Act" })).toBeInTheDocument();
  });

  it("uses h2 when asked", () => {
    render(
      <SettingsSection title="Top" headingLevel={2}>
        <SettingRow label="r" />
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Top" })).toBeInTheDocument();
  });
});

describe("SettingRow", () => {
  it("names its control by the label and describes it by the helper line", () => {
    render(
      <SettingRow label="Wait" labelFor="wait" description="Seconds to wait" descriptionId="wait-d">
        <input id="wait" aria-describedby="wait-d" />
      </SettingRow>,
    );
    const input = screen.getByLabelText("Wait");
    expect(input).toHaveAccessibleDescription("Seconds to wait");
  });
});
