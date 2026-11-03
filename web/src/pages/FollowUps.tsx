import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import FollowUpCard from "../components/FollowUpCard";
import { EmptyState, ErrorState, LoadingState } from "../components/ui";
import type {
  FollowUp,
  InteractionSignal,
  PersonSummary,
  PlatformIdentity,
} from "../types";

const FILTERS = ["open", "snoozed", "done", "dismissed", "all"] as const;

export default function FollowUps() {
  const [filter, setFilter] = useState<string>("open");
  const [followups, setFollowups] = useState<FollowUp[] | null>(null);
  const [signals, setSignals] = useState<Map<number, InteractionSignal>>(new Map());
  const [people, setPeople] = useState<Map<number, PersonSummary>>(new Map());
  const [peopleList, setPeopleList] = useState<PersonSummary[]>([]);
  const [identities, setIdentities] = useState<Map<number, PlatformIdentity>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [followupResult, signalResult, peopleResult, identityResult] =
      await Promise.all([
        api.followups(filter === "all" ? {} : { status: filter }),
        api.signals(),
        api.people(),
        api.identities(),
      ]);
    setFollowups(followupResult);
    setSignals(new Map(signalResult.map((signal) => [signal.id, signal])));
    setPeople(new Map(peopleResult.map((person) => [person.id, person])));
    setPeopleList(peopleResult);
    setIdentities(new Map(identityResult.map((identity) => [identity.id, identity])));
  }, [filter]);

  useEffect(() => {
    load().catch(() => setError("Could not load follow-ups"));
  }, [load]);

  const changed = useCallback((message: string) => {
    setNotice(message);
    load().catch(() => setError("The change was saved, but follow-ups could not be refreshed."));
  }, [load]);

  if (error) return <ErrorState message={error} />;
  return (
    <main>
      <h1>Follow-ups</h1>
      <p className="page-intro">
        Manage decisions you have confirmed and candidates still awaiting your
        judgment. Review items become obligations only when you mark them.
      </p>
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
      {notice && (
        <p className="feedback feedback-success" role="status">
          {notice}
        </p>
      )}
      {!followups ? (
        <LoadingState />
      ) : followups.length === 0 ? (
        <EmptyState>No follow-ups with this status.</EmptyState>
      ) : (
        <div className="card-list">
          {followups.map((followup) => {
            const signal = followup.signal_id
              ? signals.get(followup.signal_id) ?? null
              : null;
            const personId = followup.person_id ?? signal?.person_id ?? null;
            return (
              <FollowUpCard
                key={followup.id}
                followup={followup}
                signal={signal}
                person={personId ? people.get(personId) ?? null : null}
                identity={signal?.identity_id
                  ? identities.get(signal.identity_id) ?? null
                  : null}
                people={peopleList}
                onChanged={changed}
              />
            );
          })}
        </div>
      )}
    </main>
  );
}
