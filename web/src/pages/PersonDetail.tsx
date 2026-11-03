import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import FollowUpControls from "../components/FollowUpControls";
import { ErrorState, LoadingState } from "../components/ui";
import { formatDateTime, humanize } from "../format";
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
  const [notesFeedback, setNotesFeedback] = useState<string | null>(null);
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

  if (error) return <ErrorState message={error} />;
  if (!detail) return <LoadingState />;
  const { person, identities, signals, followups } = detail;
  const nameNeedle = person.display_name.trim().toLowerCase();
  const relatedIdentityIds = new Set(
    signals.map((signal) => signal.identity_id).filter(Boolean),
  );
  const relevantUnresolved = unresolved.filter((identity) =>
    relatedIdentityIds.has(identity.id) ||
    identity.value_normalized.toLowerCase() === nameNeedle ||
    identity.value_display.toLowerCase().includes(nameNeedle),
  );
  const relevantUnassigned = unassigned.filter((signal) =>
    signal.actor_candidate?.trim().toLowerCase() === nameNeedle,
  );
  const saveNotes = () => {
    setNotesFeedback(null);
    api.updatePerson(person.id, { notes })
      .then(() => {
        setNotesFeedback("Notes saved.");
        load();
      })
      .catch(() => setNotesFeedback("Notes could not be saved."));
  };
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
        <button type="button" onClick={saveNotes}>
          Save notes
        </button>
        {notesFeedback && (
          <p className="feedback feedback-success" role="status">
            {notesFeedback}
          </p>
        )}
      </section>
      <section>
        <h2>Identities</h2>
        {identities.length === 0 ? (
          <p>No linked identities yet.</p>
        ) : (
          <ul>
            {identities.map((identity) => (
              <li key={identity.id}>
                {identity.value_display} on {humanize(identity.platform)} (
                {humanize(identity.match_status)} via {humanize(identity.match_method ?? "unknown")})
              </li>
            ))}
          </ul>
        )}
        {relevantUnresolved.length > 0 && (
          <>
            <h3>Possible identity for this person</h3>
            <p>
              Only unresolved identities connected to this person's timeline or
              exact identity value are shown here. Use Today to resolve other
              identities in context.
            </p>
            <ul>
              {relevantUnresolved.map((identity) => (
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
                [{humanize(signal.platform)}] {humanize(signal.kind)} from{" "}
                {signal.actor_candidate ?? "unknown"} ·{" "}
                <time dateTime={signal.occurred_at}>
                  {formatDateTime(signal.occurred_at)}
                </time>{" "}
                <small>
                  parser {signal.parser_name} v{signal.parser_version} /{" "}
                  {humanize(signal.status)}
                  {signal.summary ? ` / ${signal.summary}` : ""}
                </small>
              </li>
            ))}
          </ul>
        )}
        {relevantUnassigned.length > 0 && (
          <>
            <h3>Name-only signal matching this person</h3>
            <p>
              A matching display name is not an identity. Assign only if you
              recognize this specific interaction.
            </p>
            <ul>
              {relevantUnassigned.map((signal) => (
                <li key={signal.id}>
                  [{humanize(signal.platform)}] {humanize(signal.kind)} from {signal.actor_candidate}
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
                  {humanize(followup.kind)} / {humanize(followup.status)}
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
