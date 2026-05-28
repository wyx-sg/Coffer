// frontend/src/pages/resources/ResourcesToolbar.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ResourcesToolbar } from "./ResourcesToolbar";

describe("ResourcesToolbar", () => {
  test("renders the search input and status filter", () => {
    render(
      <ResourcesToolbar search="" onSearchChange={vi.fn()} status="all" onStatusChange={vi.fn()} />,
    );
    // Search field is accessible
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // Status filter trigger is rendered
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  test("onSearchChange fires with the typed value", () => {
    const onSearchChange = vi.fn();
    render(
      <ResourcesToolbar
        search=""
        onSearchChange={onSearchChange}
        status="all"
        onStatusChange={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "github" },
    });
    expect(onSearchChange).toHaveBeenCalledWith("github");
  });

  test("shows the clear button when search has text and calls onSearchChange('') on click", () => {
    const onSearchChange = vi.fn();
    render(
      <ResourcesToolbar
        search="github"
        onSearchChange={onSearchChange}
        status="all"
        onStatusChange={vi.fn()}
      />,
    );
    const clearBtn = screen.getByRole("button", { name: /clear/i });
    expect(clearBtn).toBeInTheDocument();
    fireEvent.click(clearBtn);
    expect(onSearchChange).toHaveBeenCalledWith("");
  });

  test("shows the current search value in the input", () => {
    render(
      <ResourcesToolbar
        search="filesystem"
        onSearchChange={vi.fn()}
        status="all"
        onStatusChange={vi.fn()}
      />,
    );
    const input = screen.getByRole("textbox") as HTMLInputElement;
    expect(input.value).toBe("filesystem");
  });

  test("onStatusChange fires with the selected status value", async () => {
    const onStatusChange = vi.fn();
    render(
      <ResourcesToolbar
        search=""
        onSearchChange={vi.fn()}
        status="all"
        onStatusChange={onStatusChange}
      />,
    );

    // Open the Radix Select by pointer-down + click on the trigger (combobox role)
    const trigger = screen.getByRole("combobox");
    fireEvent.pointerDown(trigger, { button: 0 });
    fireEvent.click(trigger);

    // The Select portal renders options in the document; pick "Enabled"
    const enabledOption = await screen.findByRole("option", { name: "Enabled" });
    fireEvent.click(enabledOption);

    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("enabled"));
  });
});
