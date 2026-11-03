import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import FollowUpControls from "../components/FollowUpControls";
import type { FollowUp } from "../types";

const FILTERS = ["open", "snoozed", "done", "dismissed", "all"] as const;

export default function FollowUps() {
  const [filter, setFilter] = useState<string>("open");
  const [followups, setFollowups] = useState<FollowUp[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .followups(filter === "all" ? {} : { status: filter })
      .then(setFollowups)
      .catch(() => setError("Could not load follow-ups"));
  }, [filter]);

  useEffect(load, [load]);

  if (error) return <p role="alert">{error}</p>;
  return (
    <main>
      <h1>Follow-ups</h1>
      <label>
        Status{" "}
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          {FILTERS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <p>
        <small>
          Review items are candidates from notifications. They become reply
          obligations only when you mark them.
        </small>
      </p>
      {!followups ? (
        <p>Loading…</p>
      ) : followups.length === 0 ? (
        <p>No follow-ups with this status.</p>
      ) : (
        <ul>
          {followups.map((followup) => (
            <li key={followup.id}>
              {followup.title}{" "}
              <small>
                {followup.kind} / {followup.status}
                {followup.person_id
                  ? ` / person ${followup.person_id}`
                  : " / unassigned"}
              </small>
              <FollowUpControls followup={followup} onChanged={load} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
