import { api } from "../api";
import type { FollowUp } from "../types";
import { Button } from "./ui";

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
    <span className="followup-controls">
      {!resolved && (
        <>
          <Button onClick={act({ status: "done" })}>Done</Button>
          <Button variant="quiet" onClick={act({ status: "dismissed" })}>
            Dismiss
          </Button>
          {followup.status !== "snoozed" && (
            <Button
              onClick={act({ status: "snoozed", snoozed_until: snoozeUntil() })}
            >
              Snooze 7 days
            </Button>
          )}
        </>
      )}
      {resolved && <Button onClick={act({ status: "open" })}>Reopen</Button>}
      {followup.kind === "review" && !resolved && (
        <Button variant="primary" onClick={act({ kind: "reply" })}>
          Mark as needs reply
        </Button>
      )}
    </span>
  );
}
