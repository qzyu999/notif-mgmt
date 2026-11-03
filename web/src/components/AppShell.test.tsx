import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AppShell from "./AppShell";

describe("AppShell", () => {
  it("provides skip navigation and marks the active route", () => {
    render(
      <AppShell route="#/people/1">
        <p>Relationship workspace</p>
      </AppShell>,
    );

    expect(screen.getByText("Skip to main content")).toBeTruthy();
    expect(screen.getByText("Relationship Ledger")).toBeTruthy();
    expect(screen.getByRole("link", { name: "People" }).getAttribute("aria-current"))
      .toBe("page");
    expect(screen.getByRole("link", { name: "Today" }).getAttribute("aria-current"))
      .toBeNull();
    expect(screen.getByText("Relationship workspace")).toBeTruthy();
  });
});
