import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import FollowUpCard from "../components/FollowUpCard";
import { EmptyState, ErrorState, LoadingState } from "../components/ui";
import type {
  FollowUp,
  InteractionSignal,
  PersonSummary,
  PlatformIdentity,
  TodayResponse,
} from "../types";

type Context = {
  signals: Map<number, InteractionSignal>;
  people: Map<number, PersonSummary>;
  identities: Map<number, PlatformIdentity>;
  peopleList: PersonSummary[];
};

function Section({
  title,
  description,
  items,
  empty,
  context,
  onChanged,
}: {
  title: string;
  description: string;
  items: FollowUp[];
  empty: string;
  context: Context;
  onChanged: (message: string) => void;
}) {
  return (
    <section>
      <h2>{title}</h2>
      <p className="section-description">{description}</p>
      {items.length === 0 ? (
        <EmptyState>{empty}</EmptyState>
      ) : (
        <div className="card-list">
          {items.map((followup) => {
            const signal = followup.signal_id
              ? context.signals.get(followup.signal_id) ?? null
              : null;
            const personId = followup.person_id ?? signal?.person_id ?? null;
            return (
              <FollowUpCard
                key={followup.id}
                followup={followup}
                signal={signal}
                person={personId ? context.people.get(personId) ?? null : null}
                identity={signal?.identity_id
                  ? context.identities.get(signal.identity_id) ?? null
                  : null}
                people={context.peopleList}
                onChanged={onChanged}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

export default function Today() {
  const [today, setToday] = useState<TodayResponse | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [todayResult, signals, people, identities] = await Promise.all([
      api.today(),
      api.signals(),
      api.people(),
      api.identities(),
    ]);
    setToday(todayResult);
    setContext({
      signals: new Map(signals.map((signal) => [signal.id, signal])),
      people: new Map(people.map((person) => [person.id, person])),
      identities: new Map(identities.map((identity) => [identity.id, identity])),
      peopleList: people,
    });
  }, []);

  useEffect(() => {
    load().catch(() => setError("Could not load Today"));
  }, [load]);

  const changed = useCallback((message: string) => {
    setNotice(message);
    load().catch(() => setError("The change was saved, but Today could not be refreshed."));
  }, [load]);

  const counts = useMemo(() => {
    if (!today) return null;
    return {
      confirmed: today.due.length + today.snoozed_ready.length,
      candidates: today.review_candidates.length,
    };
  }, [today]);

  if (error) return <ErrorState message={error} />;
  if (!today || !context) return <LoadingState />;
  return (
    <main>
      <h1>Today</h1>
      <p className="page-intro">
        Start with people who contacted you. Confirmed actions come first;
        notification candidates stay provisional until you decide.
      </p>
      {counts && (
        <p className="today-summary" aria-live="polite">
          {counts.confirmed} confirmed action{counts.confirmed === 1 ? "" : "s"} ·{" "}
          {counts.candidates} review candidate{counts.candidates === 1 ? "" : "s"}
        </p>
      )}
      {notice && (
        <p className="feedback feedback-success" role="status">
          {notice}
        </p>
      )}
      <Section
        title="Due and overdue"
        description="Obligations you confirmed and scheduled."
        items={today.due}
        empty="Nothing due."
        context={context}
        onChanged={changed}
      />
      <Section
        title="Snoozes that have expired"
        description="Items you postponed that are ready to reconsider."
        items={today.snoozed_ready}
        empty="No expired snoozes."
        context={context}
        onChanged={changed}
      />
      <Section
        title="Review candidates"
        description="A notification created these candidates. It does not prove that a reply is owed."
        items={today.review_candidates}
        empty="No review candidates. A notification alone never means a reply is owed."
        context={context}
        onChanged={changed}
      />
    </main>
  );
}
