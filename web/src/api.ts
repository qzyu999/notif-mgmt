import type {
  FollowUp,
  InteractionSignal,
  Person,
  PersonDetail,
  PersonSummary,
  PlatformIdentity,
  SourceStatus,
  TodayResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const send = <T,>(method: string, path: string, body: unknown) =>
  request<T>(path, { method, body: JSON.stringify(body) });

export const api = {
  today: () => get<TodayResponse>("/api/v1/today"),
  people: () => get<PersonSummary[]>("/api/v1/people"),
  person: (id: number) => get<PersonDetail>(`/api/v1/people/${id}`),
  identities: (matchStatus?: string) =>
    get<PlatformIdentity[]>(
      `/api/v1/identities${matchStatus ? `?match_status=${matchStatus}` : ""}`,
    ),
  followups: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return get<FollowUp[]>(`/api/v1/followups${query ? `?${query}` : ""}`);
  },
  signals: () => get<InteractionSignal[]>("/api/v1/signals"),
  sources: () => get<SourceStatus[]>("/api/v1/sources"),
  createPerson: (displayName: string, notes = "") =>
    send<Person>("POST", "/api/v1/people", {
      display_name: displayName,
      notes,
    }),
  linkIdentity: (identityId: number, personId: number) =>
    send<PlatformIdentity>("POST", `/api/v1/identities/${identityId}/link`, {
      person_id: personId,
    }),
  assignSignal: (signalId: number, personId: number) =>
    send<unknown>("POST", `/api/v1/signals/${signalId}/assign`, {
      person_id: personId,
    }),
  updateFollowUp: (id: number, changes: Partial<FollowUp>) =>
    send<FollowUp>("PATCH", `/api/v1/followups/${id}`, changes),
  updatePerson: (
    id: number,
    changes: { display_name?: string; notes?: string },
  ) => send<Person>("PATCH", `/api/v1/people/${id}`, changes),
};
