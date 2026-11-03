import { useMemo, useState } from "react";

import { api } from "../api";
import { formatDateTime, humanize, initials } from "../format";
import type {
  FollowUp,
  InteractionSignal,
  Person,
  PersonSummary,
  PlatformIdentity,
} from "../types";
import { Button, ErrorState, SemanticBadge } from "./ui";

type PersonOption = Person | PersonSummary;

function snoozeUntil(): string {
  const date = new Date(Date.now() + 7 * 24 * 3600 * 1000);
  return date.toISOString().replace(/\.\d+Z$/, "Z");
}

export default function FollowUpCard({
  followup,
  signal,
  person,
  identity,
  people,
  onChanged,
}: {
  followup: FollowUp;
  signal: InteractionSignal | null;
  person: PersonOption | null;
  identity: PlatformIdentity | null;
  people: PersonSummary[];
  onChanged: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolverOpen, setResolverOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [newName, setNewName] = useState(
    signal?.actor_candidate ?? identity?.value_display ?? "",
  );
  const [selected, setSelected] = useState<PersonOption | null>(null);

  const displayName =
    person?.display_name ??
    signal?.actor_candidate ??
    identity?.value_display ??
    "Unknown sender";
  const identityLinked = Boolean(
    person && identity && identity.person_id === person.id,
  );
  const resolutionMode = !person && identity
    ? "identity"
    : !person && signal?.actor_candidate
      ? "signal"
      : null;
  const filteredPeople = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return people;
    return people.filter((candidate) =>
      candidate.display_name.toLowerCase().includes(needle) ||
      candidate.platforms.some((platform) => platform.toLowerCase().includes(needle)),
    );
  }, [people, query]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The change could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const update = (changes: Partial<FollowUp>, success: string) => () =>
    run(() => api.updateFollowUp(followup.id, changes), success);

  const createPerson = () =>
    run(async () => {
      const created = await api.createPerson(newName.trim());
      setSelected(created);
    }, "Person created. Confirm the link before anything is associated.");

  const confirmResolution = () => {
    if (!selected) return;
    if (resolutionMode === "identity" && identity) {
      void run(
        () => api.linkIdentity(identity.id, selected.id),
        `Identity ${identity.value_display} linked to ${selected.display_name}. Related interactions now use this person.`,
      );
    } else if (resolutionMode === "signal" && signal) {
      void run(
        () => api.assignSignal(signal.id, selected.id),
        `Interaction assigned to ${selected.display_name}. The display name itself was not treated as an identity.`,
      );
    }
  };

  return (
    <article className="followup-card" aria-label={`Follow-up from ${displayName}`}>
      <div className="card-heading">
        <span className="person-avatar" aria-hidden="true">
          {initials(displayName)}
        </span>
        <div>
          <h3>{displayName}</h3>
          <p className="card-meta">
            {signal
              ? `${humanize(signal.kind)} via ${humanize(signal.platform)} · `
              : "Follow-up · "}
            {signal ? (
              <time dateTime={signal.occurred_at}>{formatDateTime(signal.occurred_at)}</time>
            ) : (
              formatDateTime(followup.created_at)
            )}
          </p>
        </div>
        {followup.kind === "review" ? (
          <SemanticBadge tone="candidate">Review candidate</SemanticBadge>
        ) : (
          <SemanticBadge tone="confirmed">You confirmed</SemanticBadge>
        )}
      </div>

      <div className="context-block">
        <div className="context-label">
          <SemanticBadge tone="evidence">Source evidence</SemanticBadge>
          <span>Available message context</span>
        </div>
        <p>{signal?.summary || "No message context is stored for this item."}</p>
        {signal && (
          <p className="inference-line">
            <SemanticBadge tone="inference">Parser inference</SemanticBadge>
            <span>
              {humanize(signal.kind)}; parser {signal.parser_name} v{signal.parser_version};
              confidence {Math.round(signal.confidence * 100)}%.
            </span>
          </p>
        )}
        {signal?.status === "withdrawn" && (
          <p>
            <SemanticBadge tone="withdrawn">Withdrawn</SemanticBadge> This source
            item was deleted; the historical signal is preserved.
          </p>
        )}
      </div>

      <div className="identity-line">
        {identityLinked && identity && person ? (
          <>
            <SemanticBadge tone="confirmed">Identity linked</SemanticBadge>
            <span>
              {identity.value_display} on {humanize(identity.platform)} is linked
              to {person.display_name}.
            </span>
          </>
        ) : person ? (
          <>
            <SemanticBadge tone="confirmed">Person confirmed</SemanticBadge>
            <span>This interaction is associated with {person.display_name}.</span>
          </>
        ) : identity ? (
          <>
            <SemanticBadge tone="candidate">Identity unresolved</SemanticBadge>
            <span>
              {identity.value_display} on {humanize(identity.platform)} has not
              been linked to a person.
            </span>
          </>
        ) : signal?.actor_candidate ? (
          <>
            <SemanticBadge tone="inference">Name candidate only</SemanticBadge>
            <span>
              “{signal.actor_candidate}” is a display name from the notification,
              not a confirmed identity.
            </span>
          </>
        ) : (
          <>
            <SemanticBadge tone="inference">Sender unresolved</SemanticBadge>
            <span>No confirmed person or reusable identity is available.</span>
          </>
        )}
      </div>

      {error && <ErrorState message={error} />}

      <div className="card-actions">
        {person && (
          <a className="button button-quiet" href={`#/people/${person.id}`}>
            Open person
          </a>
        )}
        {resolutionMode && (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => setResolverOpen((open) => !open)}
          >
            {resolutionMode === "identity" ? "Resolve identity" : "Assign interaction"}
          </Button>
        )}
        {followup.status === "snoozed" && (
          <Button disabled={busy} onClick={update({ status: "open" }, `${displayName}'s item was resumed.`)}>
            Resume
          </Button>
        )}
        {followup.kind === "review" && followup.status !== "done" && followup.status !== "dismissed" && (
          <Button
            variant="primary"
            disabled={busy}
            onClick={update({ kind: "reply" }, `${displayName}'s item is now marked as needing a reply.`)}
          >
            Mark as needs reply
          </Button>
        )}
        {followup.status !== "done" && followup.status !== "dismissed" && (
          <>
            <Button disabled={busy} onClick={update({ status: "done" }, `${displayName}'s item was completed.`)}>
              Done
            </Button>
            {followup.status !== "snoozed" && (
              <Button
                disabled={busy}
                onClick={update(
                  { status: "snoozed", snoozed_until: snoozeUntil() },
                  `${displayName}'s item was snoozed for 7 days.`,
                )}
              >
                Snooze 7 days
              </Button>
            )}
            <Button
              variant="quiet"
              disabled={busy}
              onClick={update({ status: "dismissed" }, `${displayName}'s item was dismissed.`)}
            >
              Dismiss
            </Button>
          </>
        )}
        {(followup.status === "done" || followup.status === "dismissed") && (
          <Button disabled={busy} onClick={update({ status: "open" }, `${displayName}'s item was reopened.`)}>
            Reopen
          </Button>
        )}
      </div>

      {resolverOpen && resolutionMode && (
        <section className="resolver" aria-label="Resolve this interaction">
          <h4>
            {resolutionMode === "identity" ? "Link this identity safely" : "Assign this interaction"}
          </h4>
          {resolutionMode === "identity" && identity ? (
            <p>
              Link <strong>{identity.value_display}</strong> on {humanize(identity.platform)}
              to a person you choose. Nothing is linked until you confirm.
            </p>
          ) : (
            <p>
              <strong>{signal?.actor_candidate}</strong> is only a display name from
              the notification. It is not an identity. You may assign this one
              interaction to a person, but no reusable identity will be created.
            </p>
          )}

          <label>
            Find a person{" "}
            <input
              aria-label="Find a person"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name or platform"
            />
          </label>
          {filteredPeople.length > 0 ? (
            <ul className="person-picker">
              {filteredPeople.map((candidate) => (
                <li key={candidate.id}>
                  <span>
                    {candidate.display_name}
                    <small> {candidate.platforms.join(", ") || "no linked platform"}</small>
                  </span>
                  <Button disabled={busy} onClick={() => setSelected(candidate)}>
                    Use {candidate.display_name}
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p>No matching person. Create one below, then confirm the association.</p>
          )}

          <div className="create-person-row">
            <label>
              New person name{" "}
              <input
                aria-label="New person name for resolution"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </label>
            <Button disabled={busy || !newName.trim()} onClick={createPerson}>
              Create person
            </Button>
          </div>

          {selected && (
            <div className="resolution-confirmation">
              <p>
                {resolutionMode === "identity" && identity
                  ? `Confirm that ${identity.value_display} belongs to ${selected.display_name}. Related signals and follow-ups for that identity will use this person.`
                  : `Confirm that this interaction should be assigned to ${selected.display_name}. This does not create or link an identity.`}
              </p>
              <Button variant="primary" disabled={busy} onClick={confirmResolution}>
                {resolutionMode === "identity"
                  ? `Confirm link to ${selected.display_name}`
                  : `Confirm assignment to ${selected.display_name}`}
              </Button>
              <Button variant="quiet" disabled={busy} onClick={() => setSelected(null)}>
                Cancel selection
              </Button>
            </div>
          )}
          <Button variant="quiet" onClick={() => setResolverOpen(false)}>
            Close resolver
          </Button>
        </section>
      )}
    </article>
  );
}
