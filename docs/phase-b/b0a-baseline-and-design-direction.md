# Phase B B0a — baseline and design direction

Status: design review only. No UI implementation, backend contract change,
Gmail access, polling, or external inference is included.

## Baseline capture

The current UI was captured with Playwright against the synthetic CLI demo
database used by the existing end-to-end setup. The capture used desktop
1280x720 and then a 390x844 mobile viewport in the same synthetic session.
The Person Detail capture follows the existing golden-path setup actions:
create Taylor and manually link Taylor's synthetic email identity.

| Screen | Desktop | Mobile |
| --- | --- | --- |
| Today | [desktop-today.png](baseline/desktop-today.png) | [mobile-today.png](baseline/mobile-today.png) |
| People | [desktop-people.png](baseline/desktop-people.png) | [mobile-people.png](baseline/mobile-people.png) |
| Person Detail | [desktop-person-detail.png](baseline/desktop-person-detail.png) | [mobile-person-detail.png](baseline/mobile-person-detail.png) |
| Follow-ups | [desktop-followups.png](baseline/desktop-followups.png) | [mobile-followups.png](baseline/mobile-followups.png) |
| Sources | [desktop-sources.png](baseline/desktop-sources.png) | [mobile-sources.png](baseline/mobile-sources.png) |

The demo database has no Gmail sync state, so Sources correctly shows its
empty state. These screenshots are a visual baseline, not evidence of a
populated production mailbox.

## Current journeys and friction

### Daily triage

1. The user opens Today and sees due work, expired snoozes, and review
   candidates.
2. Today is read-only, so no candidate can be decided there.
3. The user switches to Follow-ups and finds the same item again.
4. Each candidate presents Done, Dismiss, Snooze 7 days, and Mark as needs
   reply with the same visual weight.

The baseline demo's two candidates therefore require a route change and
present eight similarly weighted actions. This is the largest avoidable
daily friction.

### Identity resolution

1. People shows an unresolved identity, but gives no resolution action.
2. The user creates a person first.
3. The user opens that person and scans the unresolved identity list there.
4. The user links the identity.
5. Name-only signals are handled through a separate list on the same page,
   but the distinction is conveyed mainly by heading text.

The flow preserves A6 safety, but it starts from the destination person
instead of from the unresolved item. It also repeats the global list on
every Person Detail page, so scanning and wrong-selection risk grow with
data volume.

### Relationship review

People communicates platform count and last interaction as raw metadata.
Person Detail starts with Notes rather than relationship state or next
actions. The timeline is useful and includes parser provenance, but it is a
single undifferentiated list. Follow-ups are below identities and timeline,
and the user must interpret raw kind, status, and timestamp strings.

### Follow-up management

Follow-ups has one status filter. Open candidates and confirmed obligations
remain together, the person is shown as a numeric ID, and there is no direct
person navigation or signal context beyond the generated title. The
candidate-versus-obligation explanation is correct but visually weak.

### Source trust

Sources correctly explains sender-domain matching and shows only sync
metadata. In a populated state, its information is still presented as dense
implementation fields. In the baseline it has no sync state, so the main
visible lesson is that the empty state does not explain the purpose or
health model of the page.

## Baseline hierarchy findings

- The primary navigation is four identical blue text links with no product
  mark, active state, counts, search, or resolution entry point.
- Page titles provide almost all hierarchy. Section titles, item titles,
  metadata, and controls otherwise sit in one flat list plane.
- Muted small text carries important distinctions such as person assignment,
  parser version, status, and platform.
- Large empty areas in the synthetic baseline are partly a small-data
  artifact, but there are no reusable empty, loading, success, or grouped
  content structures to carry a richer data set.
- On mobile, content remains readable, but follow-up actions wrap into
  multiple button rows and the same flat hierarchy persists.
- Native links, buttons, labels, and selects provide a usable accessibility
  foundation. Visible focus treatment, skip navigation, active-route
  semantics, responsive action patterns, and mutation feedback are absent.

## API capability audit

The proposed Phase B workflows can be built without backend changes by
composing existing `/api/v1` responses in the browser.

| Capability | Existing support | B0a conclusion |
| --- | --- | --- |
| Person lookup | `GET /people` returns names, platforms, identity counts, last interaction, and open-follow-up count. `GET /identities` returns identity values and linked person IDs. `GET /signals` returns actor candidates, platforms, and person IDs. | Client-side lookup by person name, identity value, platform, and actor candidate is feasible for the local single-user data scale. There is no server-side search or pagination, so this should be revisited only if measured local data volume makes list loading slow. |
| Today context | `GET /today` already separates due, snoozed-ready, and review candidates. Follow-ups carry `person_id`, `signal_id`, kind, status, due and snooze times, `created_by`, and confidence. | Existing follow-up actions and grouping need no backend change. Person and signal context can be joined from `GET /people` and `GET /signals`. |
| Follow-up context | `GET /followups` supports status, kind, and person filters. `GET /signals` can map a follow-up's `signal_id` to platform, kind, summary, actor candidate, occurred time, parser provenance, and active or withdrawn status. | Cards can show person, platform, summary, timing, inference provenance, and state without a new endpoint. |
| Identity resolution | `GET /identities?match_status=unmatched`, `GET /people`, `POST /people`, `POST /identities/{id}/link`, and `POST /signals/{id}/assign` already exist. `POST /people/{id}/identities` also exists, although the frontend API wrapper does not expose it yet. | A resolution flow that starts from the unresolved identity or signal is feasible. It must keep exact identity linking distinct from name-only signal assignment. |
| Person relationship view | `GET /people/{id}` returns the person, identities, signals newest first, and follow-ups. | A summary header, grouped actions, and reverse-chronological timeline are feasible from this response alone. |
| Due and snooze editing | `PATCH /followups/{id}` supports status, kind, note, `due_at`, and `snoozed_until`, including explicit clearing through fields present in the request. | Follow-up management can be completed in the frontend without a contract change. |
| Sources | `GET /sources` returns account, cursor presence, sync and recovery times, error code and message, and gap count. | Conservative plain-language health summaries can be derived without inventing new guarantees. |

### Explicit API limitations

- There is no endpoint for the underlying source-event record behind a
  signal. The UI can show the signal's stored summary and provenance, but
  should not pretend it can show the original notification, sender record,
  subject, thread, or conversation link unless a future reviewed backend
  slice adds a safe source-evidence response.
- Person summaries do not include identity values; lookup requires joining
  `GET /identities` in the browser. That is acceptable for B0-B3 at local
  scale but is not a scalable search contract.
- Follow-ups do not embed person or signal objects. Browser joins are
  sufficient, but components must tolerate an unassigned person or a missing
  signal reference.
- List endpoints have no pagination. This is a known local-first scale
  assumption, not a B0 blocker.
- The frontend request helper currently discards API error detail. richer
  mutation feedback can be implemented in the frontend by reading the error
  response; no backend change is required for that improvement.

No missing API capability blocks B0b or the recommended B1-B3 workflows.
A source-evidence detail view would be a separate reviewed decision if B4
requires more than signal summary and provenance.

## Design direction A — Relationship Ledger

### Concept

A private correspondence ledger: calm, archival, and deliberate. It treats
the product as a trusted record of relationships rather than a social feed
or generic operations dashboard.

### Typography and density

- Headings use a restrained serif system stack such as Charter, Georgia,
  or `ui-serif` to give people and relationship records a durable feel.
- Body and controls use the system sans stack for clarity.
- Metadata, timestamps, parser names, and source values use a monospace or
  tabular treatment sparingly.
- Medium-low density with generous row padding, clear section rhythm, and
  a maximum reading width. Dense tables are reserved for People lookup and
  resolved follow-up history.

### Palette

- Warm paper background `#F7F3EC`.
- Ink text `#20251F`.
- Deep moss primary `#48634F`.
- Muted clay accent `#B2603F` for attention that is not an error.
- Cool slate for source metadata, warm amber for inference, and deep green
  for user confirmation.
- Full light and dark token sets are defined in B0b; status never relies on
  color alone.

### Navigation and layout

- Desktop uses a quiet left rail with product name, primary routes, counts,
  and a persistent person lookup field.
- Mobile uses a compact top bar with the same routes available without
  hiding primary work behind an icon-only menu.
- Today is a focused action list, People is a searchable directory table,
  Person Detail uses a summary header plus timeline, and Sources uses
  account record cards.

### Cards, tables, and timeline

- Cards resemble ledger entries: a firm left rule, person identity first,
  context second, actions last.
- People uses scan-friendly rows rather than decorative cards.
- The relationship timeline uses a vertical rule and date groups.
- Technical provenance is available in a secondary metadata line or detail
  disclosure instead of competing with the interaction summary.

### Evidence, inference, and confirmed state

- **Source evidence:** square slate marker, solid left rule, label
  "Source evidence", timestamp, platform, and stored summary.
- **Parser inference:** dashed amber outline, label "Parser inference",
  inferred kind, actor candidate where present, confidence, and parser
  version in secondary text. A display name is explicitly "name candidate
  only" when it is not a linked identity.
- **User-confirmed obligation:** filled moss marker and check label "You
  confirmed", solid border, and action language such as "Reply you marked"
  rather than system-asserted urgency.
- Review candidates stay visually provisional: outlined, amber-accented,
  and grouped separately from confirmed obligations.
- Withdrawn signals become muted historical ledger entries with a clear
  withdrawn label, never danger-red active alerts.

### Component principles

- One primary action per item; lower-frequency actions move to an overflow
  menu.
- Status is text plus shape or border treatment, not color alone.
- Provenance is one click or one glance away but does not dominate.
- Every mutation has pending, success, and error feedback.
- Components use shared tokens and predictable focus order in both pointer
  and keyboard use.

## Design direction B — Signal Console

### Concept

A precise communications console for rapid scanning and triage. It favors
density, split panes, and keyboard-led operation over editorial warmth.

### Typography and density

- System sans throughout, with uppercase monospace micro-labels for state
  and provenance.
- Compact rows, sticky list headers, and master-detail panes on desktop.
- Designed first for scanning many signals quickly, with details opening in
  an adjacent inspector.

### Palette

- Graphite background `#12161C` in dark mode and pale slate `#EEF1F4` in
  light mode.
- Cyan for source evidence, violet for parser inference, green for user
  confirmation, and red only for errors or destructive attention.
- High-contrast surfaces and thin dividers produce a technical, instrument
  panel feel in both modes.

### Navigation and layout

- A top command bar contains product identity, global search, source state,
  and primary navigation tabs.
- Today and Follow-ups use queue tables; People uses a dense directory;
  Person Detail uses a split timeline and inspector.
- Mobile collapses the inspector into a detail route or bottom sheet.

### Cards, tables, and timeline

- Cards are minimized in favor of rows, tables, queues, and inspector panes.
- Timeline events use compact monospace timestamps and platform codes.
- Follow-up queues expose bulk scanning patterns, though actions remain
  individual and deliberate.

### Evidence, inference, and confirmed state

- **Source evidence:** cyan square marker and monospace source metadata.
- **Parser inference:** violet dashed chip with parser and confidence.
- **User-confirmed obligation:** solid green row marker and filled
  confirmation chip.
- Review candidates use an outlined violet or amber chip and remain in a
  separate queue from confirmed obligations.
- Withdrawn records use struck-through or muted console styling plus text.

### Component principles

- Optimize for repeat scanning, stable column alignment, and keyboard focus.
- Keep the primary action visible and secondary actions in menus.
- Use compact but explicit state labels.
- Preserve a visible audit trail for every derived or confirmed state.

## Recommendation

Choose **Relationship Ledger** as the Phase B identity, borrowing Signal
Console's searchable directory, stable row alignment, and keyboard-first
discipline without adopting its generic dashboard appearance.

Reasons:

1. The product's core value is remembered relationship context, not raw
   message throughput. A ledger metaphor reinforces continuity, evidence,
   and deliberate confirmation.
2. The visual distinction between source evidence, parser inference, and
   user confirmation is clearer when geometry and language carry the
   distinction. Relationship Ledger makes that taxonomy feel native rather
   than like system diagnostics.
3. A calm medium-density interface reduces the urgency that notification
   products often manufacture. That supports the rule that a notification
   alone never proves a reply is owed.
4. Serif headings used sparingly, warm paper surfaces, and moss and clay
   accents create a recognizable local-first identity without external
   fonts, hosted assets, or a generic SaaS template.
5. Signal Console is efficient but risks making the product feel like a
   monitoring dashboard. Its strongest ideas are interaction patterns that
   can be incorporated without taking on its visual identity.

## B0b entry criteria

B0b should implement only the agreed foundation:

- Relationship Ledger design tokens for light and dark modes.
- Application shell and primary navigation with active route and skip link.
- Persistent person lookup entry point if it can be done without changing
  backend contracts.
- Focus-visible, loading, error, empty, button, badge, card, and row
  primitives.
- Mutation feedback primitives that later screens can reuse.
- Baseline screenshot comparison at the same desktop and mobile sizes.

No screen workflow redesign belongs in B0b. Today, People, Person Detail,
Follow-ups, and Sources adopt the foundation incrementally in B1-B5.
