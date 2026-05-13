import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import App from "@/App";

describe("App wired with real providers", () => {
  it("renders inside a QueryClientProvider without error", () => {
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Coffer")).toBeInTheDocument();
    expect(
      screen.getByText(/Local-first AI agent vault/i),
    ).toBeInTheDocument();
  });
});
