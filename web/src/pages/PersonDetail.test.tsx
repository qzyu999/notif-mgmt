import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import PersonDetail from "./PersonDetail";

vi.mock("../api", () => ({
  api: {
    person: vi.fn(),
    identities: vi.fn(),
    signals: vi.fn(),
    linkIdentity: vi.fn(),
    assignSignal: vi.fn(),
    updatePerson: vi.fn(),
    updateFollowUp: vi.fn(),
  },
}));

const person = {
  id: 1,
  kind: "person",
  display_name: "Taylor",
  notes: "old notes",
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
};

describe("PersonDetail", () => {
  it("shows timeline provenance, linking, and saves notes", async () => {
    vi.mocked(api.person).mockResolvedValue({
      person,
      identities: [],
      signals: [
        {
          id: 5,
          source_event_id: 5,
          identity_id: null,
          person_id: 1,
          platform: "email",
          kind: "direct_email",
          occurred_at: "2026-11-02T17:10:00Z",
          summary: "hello",
          actor_candidate: "Taylor",
          confidence: 0.6,
          parser_name: "generic-email",
          parser_version: "1",
          dedupe_key: "k",
          status: "active",
          created_at: "2026-11-02T00:00:00Z",
        },
      ],
      followups: [],
    });
    vi.mocked(api.identities).mockResolvedValue([
      {
        id: 9,
        person_id: null,
        platform: "reddit",
        identity_kind: "handle",
        value_normalized: "taylor",
        value_display: "u/taylor",
        match_status: "unmatched",
        match_method: "parser",
        confidence: 0.7,
        created_at: "2026-11-02T00:00:00Z",
        updated_at: "2026-11-02T00:00:00Z",
      },
    ]);
    vi.mocked(api.signals).mockResolvedValue([]);
    vi.mocked(api.updatePerson).mockResolvedValue({ ...person, notes: "new" });

    render(<PersonDetail personId={1} />);
    expect(await screen.findByText("Taylor")).toBeTruthy();
    expect(screen.getByText(/parser generic-email v1/)).toBeTruthy();
    expect(screen.getByText(/u\/taylor on reddit/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "new" },
    });
    fireEvent.click(screen.getByText("Save notes"));
    expect(vi.mocked(api.updatePerson)).toHaveBeenCalledWith(1, { notes: "new" });
  });
});
