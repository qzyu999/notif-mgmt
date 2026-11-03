// Mirrors the /api/v1 contracts in src/notif_mgmt/api.py. Presentation only:
// the frontend holds no domain rules beyond display.

export interface Person {
  id: number;
  kind: string;
  display_name: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface PersonSummary extends Person {
  identity_count: number;
  platforms: string[];
  last_interaction_at: string | null;
  open_followup_count: number;
}

export interface PlatformIdentity {
  id: number;
  person_id: number | null;
  platform: string;
  identity_kind: string;
  value_normalized: string;
  value_display: string;
  match_status: string;
  match_method: string | null;
  confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface InteractionSignal {
  id: number;
  source_event_id: number;
  identity_id: number | null;
  person_id: number | null;
  platform: string;
  kind: string;
  occurred_at: string;
  summary: string;
  actor_candidate: string | null;
  confidence: number;
  parser_name: string;
  parser_version: string;
  dedupe_key: string;
  status: string;
  created_at: string;
}

export interface FollowUp {
  id: number;
  person_id: number | null;
  signal_id: number | null;
  kind: string;
  status: string;
  title: string;
  note: string;
  due_at: string | null;
  snoozed_until: string | null;
  created_by: string;
  confidence: number | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface PersonDetail {
  person: Person;
  identities: PlatformIdentity[];
  signals: InteractionSignal[];
  followups: FollowUp[];
}

export interface TodayResponse {
  due: FollowUp[];
  snoozed_ready: FollowUp[];
  review_candidates: FollowUp[];
}

export interface SourceStatus {
  source: string;
  account_id: string;
  has_cursor: boolean;
  last_sync_completed_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  last_recovery_at: string | null;
  gap_count: number;
}
