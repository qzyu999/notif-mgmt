import { useEffect, useState } from "react";

import { api } from "../api";
import type { PersonSummary, PlatformIdentity } from "../types";

export default function People() {
  const [people, setPeople] = useState<PersonSummary[] | null>(null);
  const [unresolved, setUnresolved] = useState<PlatformIdentity[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.people(), api.identities("unmatched")])
      .then(([peopleResult, identityResult]) => {
        setPeople(peopleResult);
        setUnresolved(identityResult);
      })
      .catch(() => setError("Could not load people"));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!people) return <p>Loading…</p>;
  return (
    <main>
      <h1>People</h1>
      {people.length === 0 ? (
        <p>No people yet. Link an identity or assign a signal to create one.</p>
      ) : (
        <ul>
          {people.map((person) => (
            <li key={person.id}>
              <a href={`#/people/${person.id}`}>{person.display_name}</a>{" "}
              <small>
                {person.platforms.join(", ") || "no platforms"} /{" "}
                {person.identity_count} identities / last interaction{" "}
                {person.last_interaction_at ?? "never"} /{" "}
                {person.open_followup_count} open follow-ups
              </small>
            </li>
          ))}
        </ul>
      )}
      <section>
        <h2>Unresolved identities</h2>
        {unresolved.length === 0 ? (
          <p>Nothing unresolved. Display names alone are never linked.</p>
        ) : (
          <ul>
            {unresolved.map((identity) => (
              <li key={identity.id}>
                {identity.value_display} on {identity.platform} (
                {identity.match_status})
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
