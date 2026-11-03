import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button, EmptyState, ErrorState, LoadingState, SemanticBadge } from "./ui";

describe("shared UI primitives", () => {
  it("renders semantic evidence, inference, and confirmation badges as text", () => {
    render(
      <>
        <SemanticBadge tone="evidence">Source evidence</SemanticBadge>
        <SemanticBadge tone="inference">Parser inference</SemanticBadge>
        <SemanticBadge tone="confirmed">You confirmed</SemanticBadge>
      </>,
    );

    expect(screen.getByText("Source evidence").className).toContain("badge-evidence");
    expect(screen.getByText("Parser inference").className).toContain("badge-inference");
    expect(screen.getByText("You confirmed").className).toContain("badge-confirmed");
  });

  it("renders accessible loading, error, empty, and button states", () => {
    render(
      <>
        <LoadingState />
        <ErrorState message="Could not load" />
        <EmptyState>Nothing here yet.</EmptyState>
        <Button variant="primary">Save</Button>
      </>,
    );

    expect(screen.getByText("Loading…")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("Could not load");
    expect(screen.getByText("Nothing here yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" }).className).toContain("button-primary");
  });
});
