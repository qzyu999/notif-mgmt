import { api } from "../api";
import type { FollowUp } from "../types";

function snoozeUntil(): string {
  const date = new Date(Date.now() + 7 * 24 * 3600 * 1000);
  return date.toISOString().replace(/\.\d+Z$/, "Z");
}

export default function FollowUpControls({
  followup,
  onChanged,
}: {
  followup: FollowUp;
  onChanged: () => void;
}) {
  const act = (changes: Partial<FollowUp>) => () =>
    api.updateFollowUp(followup.id, changes).then(onChanged);
  const resolved = followup.status === "done" || followup.status === "dismissed";
  return (
    <span>
      {!resolved && (
        <>
          <button type="button" onClick={act({ status: "done" })}>
            Done
          </button>
          <button type="button" onClick={act({ status: "dismissed" })}>
            Dismiss
          </button>
          {followup.status !== "snoozed" && (
            <button
              type="button"
              onClick={act({ status: "snoozed", snoozed_until: snoozeUntil() })}
            >
              Snooze 7 days
            </button>
          )}
        </>
      )}
      {resolved && (
        <button type="button" onClick={act({ status: "open" })}>
          Reopen
        </button>
      )}
      {followup.kind === "review" && !resolved && (
        <button type="button" onClick={act({ kind: "reply" })}>
          Mark as needs reply
        </button>
      )}
    </span>
  );
}
