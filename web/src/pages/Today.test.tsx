import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import Today from "./Today";

vi.mock("../api", () => ({
  api: { today: vi.fn() },
}));

const followup = {
  id: 1,
  person_id: null,
  signal_id: 1,
  kind: "review",
  status: "open",
  title: "Review direct message notification from Alex",
  note: "",
  due_at: null,
  snoozed_until: null,
  created_by: "rule",
  confidence: 0.9,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  resolved_at: null,
};

describe("Today", () => {
  it("separates due obligations, expired snoozes, and review candidates", async () => {
    vi.mocked(api.today).mockResolvedValue({
      due: [{ ...followup, id: 2, kind: "reply", due_at: "2026-11-01T00:00:00Z" }],
      snoozed_ready: [
        { ...followup, id: 3, status: "snoozed", snoozed_until: "2026-11-01T00:00:00Z" },
      ],
      review_candidates: [followup],
    });
    render(<Today />);
    expect(await screen.findByText("Due and overdue")).toBeTruthy();
    expect(screen.getByText("Snoozes that have expired")).toBeTruthy();
    expect(screen.getByText("Review candidates")).toBeTruthy();
    expect(screen.getAllByText(/Review direct message/)).toHaveLength(3);
  });
});
