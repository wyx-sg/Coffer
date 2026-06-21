// components/chat/PendingQueue.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PendingQueue } from "./PendingQueue";

describe("PendingQueue", () => {
  test("renders nothing when the queue is empty", () => {
    const { container } = render(
      <PendingQueue pending={[]} onEdit={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("renders one row per queued message", () => {
    render(<PendingQueue pending={["first", "second"]} onEdit={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  test("edit and remove fire with the row index", () => {
    const onEdit = vi.fn();
    const onRemove = vi.fn();
    render(<PendingQueue pending={["a", "b"]} onEdit={onEdit} onRemove={onRemove} />);
    fireEvent.click(screen.getAllByRole("button", { name: /edit/i })[1]);
    expect(onEdit).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getAllByRole("button", { name: /remove/i })[0]);
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
