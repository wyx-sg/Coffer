// frontend/src/components/channel/ChannelFirstRun.test.tsx
// The page a person sees before any channel exists: what a channel is for, and
// the platforms as a bordered list whose rows open Add channel at Connect.
import { describe, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ChannelFirstRun } from "./ChannelFirstRun";

describe("first run", () => {
  acceptance("channels", "a first run offers the platforms", () => {
    const onChoose = vi.fn();
    render(<ChannelFirstRun onChoose={onChoose} />);

    expect(screen.getByText("Talk to your agents from a chat app")).toBeVisible();
    expect(screen.getByText("Choose a platform")).toBeVisible();
    // Each row says what it needs; the three benefit lines are gone.
    expect(screen.getByText("Needs App ID + secret")).toBeVisible();
    expect(screen.getByText("Needs bot token")).toBeVisible();
    expect(screen.queryByText("Answers only you")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /telegram/i }));
    expect(onChoose).toHaveBeenCalledWith("telegram");
  });
});
