import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import Today from "./Today";

vi.mock("../api", () => ({
  api: {
    today: vi.fn(),
    signals: vi.fn(),
    people: vi.fn(),
    identities: vi.fn(),
    updateFollowUp: vi.fn(),
    createPerson: vi.fn(),
    linkIdentity: vi.fn(),
    assignSignal: vi.fn(),
  },
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
const signal = {
  id: 1,
  source_event_id: 1,
  identity_id: null,
  person_id: null,
  platform: "linkedin",
  kind: "direct_message_notification",
  occurred_at: "2026-11-02T17:00:00Z",
  summary: "Alex: Interested in testing the provider onboarding flow.",
  actor_candidate: "Alex",
  confidence: 0.9,
  parser_name: "linkedin-notifications",
  parser_version: "1",
  dedupe_key: "gmail:default:m1",
  status: "active",
  created_at: "2026-11-02T00:00:00Z",
};

describe("Today", () => {
  it("separates obligations from candidates and explains who contacted you", async () => {
    vi.mocked(api.today).mockResolvedValue({
      due: [{ ...followup, id: 2, kind: "reply", due_at: "2026-11-01T00:00:00Z" }],
      snoozed_ready: [
        { ...followup, id: 3, status: "snoozed", snoozed_until: "2026-11-01T00:00:00Z" },
      ],
      review_candidates: [followup],
    });
    vi.mocked(api.signals).mockResolvedValue([
      signal,
      { ...signal, id: 2 },
      { ...signal, id: 3 },
    ] as never);
    vi.mocked(api.people).mockResolvedValue([]);
    vi.mocked(api.identities).mockResolvedValue([]);
    render(<Today />);
    expect(await screen.findByText("Due and overdue")).toBeTruthy();
    expect(screen.getByText("Snoozes that have expired")).toBeTruthy();
    expect(screen.getByText("Review candidates")).toBeTruthy();
    expect(screen.getAllByText("Alex")).toHaveLength(3);
    expect(screen.getAllByText(/Direct message notification via LinkedIn/)).toHaveLength(3);
    expect(screen.getAllByText(/Interested in testing/)).toHaveLength(3);
    expect(screen.getAllByText(/Name candidate only/)).toHaveLength(3);
  });
});
