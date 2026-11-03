import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api";
import Sources from "./Sources";

vi.mock("../api", () => ({
  api: { sources: vi.fn() },
}));

describe("Sources", () => {
  it("shows sync metadata and honest origin language", async () => {
    vi.mocked(api.sources).mockResolvedValue([
      {
        source: "gmail",
        account_id: "test@example.invalid",
        has_cursor: true,
        last_sync_completed_at: "2026-11-02T00:00:00Z",
        last_error_code: null,
        last_error_message: null,
        last_recovery_at: null,
        gap_count: 2,
      },
    ]);
    render(<Sources />);
    expect(await screen.findByText(/gmail \/ test@example\.invalid/)).toBeTruthy();
    expect(screen.getByText(/recovery gaps 2/)).toBeTruthy();
    expect(screen.getByText(/not SPF, DKIM, or DMARC authentication/)).toBeTruthy();
  });
});
