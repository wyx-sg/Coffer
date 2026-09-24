// components/chat/AttachmentChip.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AttachmentChip } from "./AttachmentChip";

describe("AttachmentChip", () => {
  test("a persisted attachment shows its name and type, with no remove control", () => {
    render(<AttachmentChip name="photo.jpg" detail="image/jpeg" mime="image/jpeg" />);
    const chip = screen.getByTestId("attachment-chip");
    expect(chip).toHaveTextContent("photo.jpg");
    expect(chip).toHaveTextContent("image/jpeg");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("an unnamed attachment gets the translated label", () => {
    render(<AttachmentChip />);
    expect(screen.getByText("Attachment")).toBeInTheDocument();
  });

  test("uploading shows its size and says so", () => {
    render(<AttachmentChip name="a.png" detail="2 KB" state="uploading" />);
    const chip = screen.getByTestId("attachment-chip");
    expect(chip).toHaveTextContent("2 KB");
    expect(chip).toHaveTextContent("Uploading…");
  });

  test("failed shows the reason in place of the size", () => {
    render(<AttachmentChip name="a.mp4" detail="2 KB" state="failed" error="Nope" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Nope");
    expect(screen.getByTestId("attachment-chip")).not.toHaveTextContent("2 KB");
  });

  test("the remove control is labelled with the file and calls back", () => {
    const onRemove = vi.fn();
    render(<AttachmentChip name="a.txt" detail="1 B" onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove a.txt" }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
