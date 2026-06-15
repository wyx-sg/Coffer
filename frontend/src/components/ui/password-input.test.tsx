// frontend/src/components/ui/password-input.test.tsx
// A masked input with an eye toggle that reveals the value so the user can
// verify what they typed.
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PasswordInput } from "./password-input";

describe("PasswordInput", () => {
  test("masks the value by default and reveals it on toggle", () => {
    render(<PasswordInput aria-label="secret" defaultValue="hunter2" />);
    const input = screen.getByLabelText("secret") as HTMLInputElement;
    expect(input.type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(input.type).toBe("text");

    fireEvent.click(screen.getByRole("button", { name: /hide/i }));
    expect(input.type).toBe("password");
  });

  test("forwards id and placeholder to the underlying input", () => {
    render(<PasswordInput id="app-secret" placeholder="enter secret" />);
    const input = screen.getByPlaceholderText("enter secret") as HTMLInputElement;
    expect(input.id).toBe("app-secret");
  });
});
