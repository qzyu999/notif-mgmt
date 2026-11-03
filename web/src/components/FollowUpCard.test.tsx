import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import FollowUpCard from "./FollowUpCard";

vi.mock("../api", () => ({
  api: {
    updateFollowUp: vi.fn(),
    createPerson: vi.fn(),
    linkIdentity: vi.fn(),
    assignSignal: vi.fn(),
  },
}));

const followup = {
  id: 3,
  person_id: null,
  signal_id: 5,
  kind: "review",
  status: "open",
  title: "Review direct email from Taylor",
  note: "",
  due_at: null,
  snoozed_until: null,
  created_by: "rule",
  confidence: 0.6,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  resolved_at: null,
};
const signal = {
  id: 5,
  source_event_id: 5,
  identity_id: 9,
  person_id: null,
  platform: "email",
  kind: "direct_email",
  occurred_at: "2026-11-02T17:10:00Z",
  summary: "I'd like to understand the privacy model.",
  actor_candidate: "Taylor",
  confidence: 0.6,
  parser_name: "generic-email",
  parser_version: "2",
  dedupe_key: "gmail:default:m1",
  status: "active",
  created_at: "2026-11-02T00:00:00Z",
};
const identity = {
  id: 9,
  person_id: null,
  platform: "email",
  identity_kind: "email",
  value_normalized: "taylor@example.invalid",
  value_display: "taylor@example.invalid",
  match_status: "unmatched",
  match_method: "parser",
  confidence: 0.6,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
};

describe("FollowUpCard", () => {
  afterEach(cleanup);
  it("explains context and unresolved identity before explicit linking", async () => {
    const onChanged = vi.fn();
    vi.mocked(api.createPerson).mockResolvedValue({
      id: 1,
      kind: "person",
      display_name: "Taylor",
      notes: "",
      created_at: "2026-11-02T00:00:00Z",
      updated_at: "2026-11-02T00:00:00Z",
    });
    vi.mocked(api.linkIdentity).mockResolvedValue({ ...identity, person_id: 1 });

    render(
      <FollowUpCard
        followup={followup}
        signal={signal}
        person={null}
        identity={identity}
        people={[]}
        onChanged={onChanged}
      />,
    );

    expect(screen.getByText("Taylor")).toBeTruthy();
    expect(screen.getByText(/Direct email via email/)).toBeTruthy();
    expect(screen.getByText(/understand the privacy model/)).toBeTruthy();
    expect(screen.getByText(/Identity unresolved/)).toBeTruthy();
    expect(screen.getByText(/taylor@example\.invalid/)).toBeTruthy();
    expect(screen.queryByText(/2026-11-02T17:10:00Z/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Resolve identity" }));
    fireEvent.click(screen.getByRole("button", { name: "Create person" }));
    await waitFor(() => expect(api.createPerson).toHaveBeenCalledWith("Taylor"));
    expect(api.linkIdentity).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm link to Taylor" }));
    await waitFor(() =>
      expect(api.linkIdentity).toHaveBeenCalledWith(9, 1),
    );
    expect(onChanged).toHaveBeenCalledWith(
      expect.stringContaining("linked to Taylor"),
    );
  });

  it("marks a candidate as a confirmed reply obligation", async () => {
    const onChanged = vi.fn();
    vi.mocked(api.updateFollowUp).mockResolvedValue({
      ...followup,
      kind: "reply",
    } as never);
    render(
      <FollowUpCard
        followup={followup}
        signal={signal}
        person={null}
        identity={identity}
        people={[]}
        onChanged={onChanged}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Mark as needs reply" }));
    await waitFor(() =>
      expect(api.updateFollowUp).toHaveBeenCalledWith(3, { kind: "reply" }),
    );
    expect(onChanged).toHaveBeenCalledWith(
      expect.stringContaining("marked as needing a reply"),
    );
  });

  it("gives a confirmed obligation Done as its primary action", () => {
    render(
      <FollowUpCard
        followup={{ ...followup, kind: "reply" }}
        signal={signal}
        person={null}
        identity={identity}
        people={[]}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByText(/You confirmed this needs attention/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Done" }).className).toContain(
      "button-primary",
    );
    expect(
      screen.queryByRole("button", { name: "Mark as needs reply" }),
    ).toBeNull();
    const dismiss = screen.getByRole("button", { name: "Dismiss" });
    expect(dismiss.className).toContain("button-quiet");
    expect(dismiss.className).not.toContain("button-danger");
  });

  it("explains that dismissing a candidate keeps the evidence", () => {
    render(
      <FollowUpCard
        followup={followup}
        signal={signal}
        person={null}
        identity={identity}
        people={[]}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByText(/does not prove a reply is owed/)).toBeTruthy();
    expect(screen.getByText(/Dismissing keeps the evidence/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Mark as needs reply" }).className,
    ).toContain("button-primary");
  });

  it("warns that an actor name alone is not an identity", async () => {
    render(
      <FollowUpCard
        followup={{ ...followup, id: 4, signal_id: 6 }}
        signal={{ ...signal, id: 6, identity_id: null, platform: "linkedin" }}
        person={null}
        identity={null}
        people={[]}
        onChanged={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Assign interaction" }));
    expect(screen.getByText(/only a display name/)).toBeTruthy();
    expect(screen.getByText(/not an identity/)).toBeTruthy();
  });
});
