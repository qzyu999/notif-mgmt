import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import People from "./People";

vi.mock("../api", () => ({
  api: { people: vi.fn(), identities: vi.fn() },
}));

describe("People", () => {
  it("renders person summaries and the unresolved identity queue", async () => {
    vi.mocked(api.people).mockResolvedValue([
      {
        id: 1,
        kind: "person",
        display_name: "Taylor",
        notes: "",
        created_at: "2026-11-02T00:00:00Z",
        updated_at: "2026-11-02T00:00:00Z",
        identity_count: 1,
        platforms: ["email"],
        last_interaction_at: "2026-11-02T17:10:00Z",
        open_followup_count: 1,
      },
    ]);
    vi.mocked(api.identities).mockResolvedValue([
      {
        id: 2,
        person_id: null,
        platform: "email",
        identity_kind: "email",
        value_normalized: "sam@example.invalid",
        value_display: "sam@example.invalid",
        match_status: "unmatched",
        match_method: "parser",
        confidence: 0.6,
        created_at: "2026-11-02T00:00:00Z",
        updated_at: "2026-11-02T00:00:00Z",
      },
    ]);
    render(<People />);
    expect(await screen.findByText("Taylor")).toBeTruthy();
    expect(screen.getByText(/1 open follow-ups/)).toBeTruthy();
    expect(screen.getByText(/sam@example\.invalid on email/)).toBeTruthy();
  });
});
