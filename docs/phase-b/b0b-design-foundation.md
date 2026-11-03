# Phase B B0b — Relationship Ledger design foundation

Status: implemented for visual review. This milestone establishes the
design system and application shell only. It does not redesign Today,
People, Person Detail, Follow-ups, or Sources workflows, and it does not
change backend contracts or behavior.

## Foundation

- Semantic CSS tokens in `web/src/styles.css` define light and dark roles
  for background, surfaces, ink, borders, primary action, focus, evidence,
  parser inference, user confirmation, candidates, withdrawn history, and
  danger states.
- The light theme uses warm paper and ink. The dark theme uses layered
  charcoal surfaces rather than pure black.
- Typography pairs restrained serif display headings with system sans body
  text and monospace metadata. No external fonts or UI frameworks were
  added.
- `AppShell` provides the Relationship Ledger sidebar, product statement,
  primary navigation, active-route semantics, and a skip link.
- Shared primitives in `web/src/components/ui.tsx` provide semantic badges,
  buttons, loading, error, and empty states. Existing screens use the
  loading and error primitives where they already had equivalent states.
- Native buttons, inputs, selects, textareas, focus-visible outlines, and
  reduced-motion behavior now share the token system.

## Semantic state language

- **Source evidence** uses a square slate badge treatment. It describes
  source-reported metadata and stored summaries only. It never claims
  cryptographic verification of message origin.
- **Parser inference** uses a dashed amber badge treatment for inferred kind,
  actor candidates, confidence, and parser provenance.
- **You confirmed** uses a filled moss badge treatment for explicit user
  decisions and confirmed obligations.
- Review candidates use the provisional inference family. Withdrawn history
  uses muted neutral treatment.

The badges are foundation components in B0b. Screen-specific adoption
continues in B1-B5 so workflows can change incrementally.

## Before-and-after captures

Baseline captures remain in `baseline/`. B0b captures use the same
synthetic demo flow and viewport sizes: desktop 1280x720 and mobile
390x844. Dark captures use browser-emulated `prefers-color-scheme: dark`.

| Screen | Desktop light | Desktop dark | Mobile light | Mobile dark |
| --- | --- | --- | --- | --- |
| Today | [desktop-light-today.png](b0b/desktop-light-today.png) | [desktop-dark-today.png](b0b/desktop-dark-today.png) | [mobile-light-today.png](b0b/mobile-light-today.png) | [mobile-dark-today.png](b0b/mobile-dark-today.png) |
| People | [desktop-light-people.png](b0b/desktop-light-people.png) | [desktop-dark-people.png](b0b/desktop-dark-people.png) | [mobile-light-people.png](b0b/mobile-light-people.png) | [mobile-dark-people.png](b0b/mobile-dark-people.png) |
| Person Detail | [desktop-light-person-detail.png](b0b/desktop-light-person-detail.png) | [desktop-dark-person-detail.png](b0b/desktop-dark-person-detail.png) | [mobile-light-person-detail.png](b0b/mobile-light-person-detail.png) | [mobile-dark-person-detail.png](b0b/mobile-dark-person-detail.png) |
| Follow-ups | [desktop-light-followups.png](b0b/desktop-light-followups.png) | [desktop-dark-followups.png](b0b/desktop-dark-followups.png) | [mobile-light-followups.png](b0b/mobile-light-followups.png) | [mobile-dark-followups.png](b0b/mobile-dark-followups.png) |
| Sources | [desktop-light-sources.png](b0b/desktop-light-sources.png) | [desktop-dark-sources.png](b0b/desktop-dark-sources.png) | [mobile-light-sources.png](b0b/mobile-light-sources.png) | [mobile-dark-sources.png](b0b/mobile-dark-sources.png) |

## Verification

- Shared component tests: 3 passed.
- Full frontend unit suite: 8 tests passed across 7 files.
- TypeScript typecheck: passed.
- Production build: passed.
- Temporary B0b Playwright capture: 1 passed.
- Existing Playwright golden path: 1 passed when run separately after
  removing the temporary capture spec, because running two data-mutating
  Playwright specs concurrently against one synthetic database creates
  duplicate synthetic people.

## Deliberately deferred

- Today action cards and triage efficiency belong to B1.
- Follow-up grouping and richer management belong to B2.
- Person lookup and identity resolution workflows belong to B3.
- Relationship timeline and Person Detail structure belong to B4.
- Sources trust-center presentation belongs to B5.
- Persistent manual theme selection is not included. B0b follows the
  operating-system color scheme through semantic tokens.
