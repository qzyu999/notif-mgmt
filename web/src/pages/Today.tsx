import { useEffect, useState } from "react";

import { api } from "../api";
import type { FollowUp, TodayResponse } from "../types";

function FollowUpRow({ followup }: { followup: FollowUp }) {
  return (
    <li>
      <span>{followup.title}</span>{" "}
      <small>
        {followup.kind} / {followup.status}
        {followup.due_at ? ` / due ${followup.due_at}` : ""}
        {followup.snoozed_until ? ` / snoozed until ${followup.snoozed_until}` : ""}
      </small>
    </li>
  );
}

function Section({
  title,
  items,
  empty,
}: {
  title: string;
  items: FollowUp[];
  empty: string;
}) {
  return (
    <section>
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p>{empty}</p>
      ) : (
        <ul>
          {items.map((followup) => (
            <FollowUpRow key={followup.id} followup={followup} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Today() {
  const [today, setToday] = useState<TodayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.today().then(setToday).catch(() => setError("Could not load Today"));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!today) return <p>Loading…</p>;
  return (
    <main>
      <h1>Today</h1>
      <Section title="Due and overdue" items={today.due} empty="Nothing due." />
      <Section
        title="Snoozes that have expired"
        items={today.snoozed_ready}
        empty="No expired snoozes."
      />
      <Section
        title="Review candidates"
        items={today.review_candidates}
        empty="No review candidates. A notification alone never means a reply is owed."
      />
    </main>
  );
}
