import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import FollowUpControls from "../components/FollowUpControls";
import type {
  InteractionSignal,
  PersonDetail as Detail,
  PlatformIdentity,
} from "../types";

export default function PersonDetail({ personId }: { personId: number }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [unresolved, setUnresolved] = useState<PlatformIdentity[]>([]);
  const [unassigned, setUnassigned] = useState<InteractionSignal[]>([]);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api.person(personId),
      api.identities("unmatched"),
      api.signals(),
    ])
      .then(([detailResult, identities, signals]) => {
        setDetail(detailResult);
        setNotes(detailResult.person.notes);
        setUnresolved(identities);
        setUnassigned(
          signals.filter((s) => s.person_id === null && s.actor_candidate),
        );
      })
      .catch(() => setError("Could not load this person"));
  }, [personId]);

  useEffect(load, [load]);

  if (error) return <p role="alert">{error}</p>;
  if (!detail) return <p>Loading…</p>;
  const { person, identities, signals, followups } = detail;
  return (
    <main>
      <h1>{person.display_name}</h1>
      <p>
        <small>{person.kind}</small>
      </p>
      <section>
        <h2>Notes</h2>
        <textarea
          aria-label="Notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={3}
          cols={50}
        />
        <button
          type="button"
          onClick={() => api.updatePerson(person.id, { notes }).then(load)}
        >
          Save notes
        </button>
      </section>
      <section>
        <h2>Identities</h2>
        {identities.length === 0 ? (
          <p>No linked identities yet.</p>
        ) : (
          <ul>
            {identities.map((identity) => (
              <li key={identity.id}>
                {identity.value_display} on {identity.platform} (
                {identity.match_status} via {identity.match_method ?? "unknown"})
              </li>
            ))}
          </ul>
        )}
        {unresolved.length > 0 && (
          <>
            <h3>Link an unresolved identity</h3>
            <ul>
              {unresolved.map((identity) => (
                <li key={identity.id}>
                  {identity.value_display} on {identity.platform}
                  <button
                    type="button"
                    onClick={() => api.linkIdentity(identity.id, person.id).then(load)}
                  >
                    Link to {person.display_name}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section>
        <h2>Interaction timeline</h2>
        {signals.length === 0 ? (
          <p>No interactions yet.</p>
        ) : (
          <ul>
            {signals.map((signal) => (
              <li key={signal.id}>
                [{signal.platform}] {signal.kind} from{" "}
                {signal.actor_candidate ?? "unknown"} at {signal.occurred_at}{" "}
                <small>
                  parser {signal.parser_name} v{signal.parser_version} /{" "}
                  {signal.status}
                  {signal.summary ? ` / ${signal.summary}` : ""}
                </small>
              </li>
            ))}
          </ul>
        )}
        {unassigned.length > 0 && (
          <>
            <h3>Assign a name-only signal</h3>
            <ul>
              {unassigned.map((signal) => (
                <li key={signal.id}>
                  [{signal.platform}] {signal.kind} from {signal.actor_candidate}
                  <button
                    type="button"
                    onClick={() => api.assignSignal(signal.id, person.id).then(load)}
                  >
                    Assign to {person.display_name}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section>
        <h2>Follow-ups</h2>
        {followups.length === 0 ? (
          <p>No follow-ups.</p>
        ) : (
          <ul>
            {followups.map((followup) => (
              <li key={followup.id}>
                {followup.title}{" "}
                <small>
                  {followup.kind} / {followup.status}
                </small>
                <FollowUpControls followup={followup} onChanged={load} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
