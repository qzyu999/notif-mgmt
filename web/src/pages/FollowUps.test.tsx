import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import FollowUps from "./FollowUps";

vi.mock("../api", () => ({
  api: {
    followups: vi.fn(),
    signals: vi.fn(),
    people: vi.fn(),
    identities: vi.fn(),
    updateFollowUp: vi.fn(),
    createPerson: vi.fn(),
    linkIdentity: vi.fn(),
    assignSignal: vi.fn(),
  },
}));

describe("FollowUps", () => {
  it("lists contextual follow-ups and completes one", async () => {
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
    vi.mocked(api.signals).mockResolvedValue([
      {
        id: 3,
        source_event_id: 3,
        identity_id: null,
        person_id: null,
        platform: "reddit",
        kind: "platform_activity",
        occurred_at: "2026-11-02T17:05:00Z",
        summary: "Someone replied to a discussion.",
        actor_candidate: null,
        confidence: 0.7,
        parser_name: "reddit-notifications",
        parser_version: "1",
        dedupe_key: "gmail:default:m3",
        status: "active",
        created_at: "2026-11-02T00:00:00Z",
      },
    ] as never);
    vi.mocked(api.people).mockResolvedValue([]);
    vi.mocked(api.identities).mockResolvedValue([]);
    vi.mocked(api.updateFollowUp).mockResolvedValue({} as never);
    render(<FollowUps />);
    expect(await screen.findByText(/Someone replied to a discussion/)).toBeTruthy();
    fireEvent.click(screen.getByText("Done"));
    await waitFor(() =>
      expect(vi.mocked(api.updateFollowUp)).toHaveBeenCalledWith(3, {
        status: "done",
      }),
    );
  });
});
