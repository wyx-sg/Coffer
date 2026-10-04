// src/components/settings/SettingsLayout.test.tsx — SettingsSection is a labelled region; SettingRow ties its label and helper to the control.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingRow, SettingsSection, SettingsTabHeader } from "./SettingsLayout";

describe("SettingsSection", () => {
  it("is a region named by its heading, with the description under it and the action beside it", () => {
    render(
      <SettingsSection title="Replies" description="How it answers" action={<button>Act</button>}>
        <SettingRow label="Row one">x</SettingRow>
      </SettingsSection>,
    );
    const region = screen.getByRole("region", { name: "Replies" });
    expect(within(region).getByRole("heading", { level: 2, name: "Replies" })).toBeInTheDocument();
    expect(within(region).getByText("How it answers")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Act" })).toBeInTheDocument();
  });

  it("uses h3 when asked", () => {
    render(
      <SettingsSection title="Sub" headingLevel={3}>
        <SettingRow label="r" />
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Sub" })).toBeInTheDocument();
  });

  it("prints no heading for a tab's only section", () => {
    render(
      <SettingsSection testId="only">
        <SettingRow label="r" />
      </SettingsSection>,
    );
    expect(screen.queryByRole("heading")).toBeNull();
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

describe("SettingsTabHeader", () => {
  it("is the tab's h1 with its one intro line", () => {
    render(<SettingsTabHeader title="Daemon" intro="The background process." />);
    expect(screen.getByRole("heading", { level: 1, name: "Daemon" })).toBeInTheDocument();
    expect(screen.getByText("The background process.")).toBeInTheDocument();
  });
});
