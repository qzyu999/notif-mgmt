import { useEffect, useState } from "react";

import { api } from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/ui";
import type { SourceStatus } from "../types";

export default function Sources() {
  const [sources, setSources] = useState<SourceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then(setSources).catch(() => setError("Could not load sources"));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!sources) return <LoadingState />;
  return (
    <main>
      <h1>Sources</h1>
      <p>
        <small>
          Platform labels come from sender-domain matching against trusted
          platform domains. That is not SPF, DKIM, or DMARC authentication of
          message origin. This page shows sync metadata only, never
          credentials or message bodies.
        </small>
      </p>
      {sources.length === 0 ? (
        <EmptyState>No sync state yet. Connect a source from the command line first.</EmptyState>
      ) : (
        <ul>
          {sources.map((source) => (
            <li key={`${source.source}:${source.account_id}`}>
              {source.source} / {source.account_id}{" "}
              <small>
                cursor {source.has_cursor ? "present" : "absent"} / last sync{" "}
                {source.last_sync_completed_at ?? "never"} / last error{" "}
                {source.last_error_code ?? "none"} / recovery gaps{" "}
                {source.gap_count} / last recovery{" "}
                {source.last_recovery_at ?? "never"}
              </small>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
