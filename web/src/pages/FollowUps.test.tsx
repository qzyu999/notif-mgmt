import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import FollowUps from "./FollowUps";

vi.mock("../api", () => ({
  api: { followups: vi.fn(), updateFollowUp: vi.fn() },
}));

describe("FollowUps", () => {
  it("lists open follow-ups and completes one", async () => {
    vi.mocked(api.followups).mockResolvedValue([
      {
        id: 3,
        person_id: null,
        signal_id: 3,
        kind: "review",
        status: "open",
        title: "Review platform activity from reddit",
        note: "",
        due_at: null,
        snoozed_until: null,
        created_by: "rule",
        confidence: 0.7,
        created_at: "2026-11-02T00:00:00Z",
        updated_at: "2026-11-02T00:00:00Z",
        resolved_at: null,
      },
    ]);
    vi.mocked(api.updateFollowUp).mockResolvedValue({} as never);
    render(<FollowUps />);
    expect(
      await screen.findByText(/Review platform activity from reddit/),
    ).toBeTruthy();
    fireEvent.click(screen.getByText("Done"));
    expect(vi.mocked(api.updateFollowUp)).toHaveBeenCalledWith(3, {
      status: "done",
    });
  });
});
