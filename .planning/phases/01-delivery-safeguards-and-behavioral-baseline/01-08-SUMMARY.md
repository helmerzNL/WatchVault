---
phase: 01-delivery-safeguards-and-behavioral-baseline
plan: "08"
subsystem: browser-evidence
tags: [playwright, chromium, axe, visual-regression, api-fixture]
requires:
  - phase: 01-delivery-safeguards-and-behavioral-baseline
    provides: Pinned Playwright stack and frontend component harness
provides:
  - Four deterministic Chromium desktop/mobile and dark/light projects
  - Fail-closed stateful same-origin API fixture
  - Keyboard-driven dashboard-to-watch-history reference journey
  - Four axe and generation-ready visual checkpoints per project
affects: [01-09, 01-10, 04-adaptive-shell-and-global-scope, 08-cross-app-hardening-and-legacy-removal]
tech-stack:
  added: []
  patterns: [stateful route interception, exact mutation contracts, keyboard navigation evidence, deferred visual baseline generation]
key-files:
  created: [frontend/playwright.config.ts, frontend/e2e/fixtures/data.ts, frontend/e2e/fixtures/api.ts, frontend/e2e/reference-journey.spec.ts]
  modified: [.gitignore, frontend/index.html, frontend/src/lib/useFetch.ts, frontend/src/pages/Search.tsx, frontend/src/styles/app.css, frontend/src/styles/tokens.css]
key-decisions:
  - "Visual assertions are declared now, but baseline generation remains exclusively owned by pinned Linux CI and human approval."
  - "The nonvisual @smoke path executes the full journey and all four axe checkpoints without requiring absent snapshots."
  - "Project-specific visible navigation is activated by keyboard so desktop and mobile both prove focus reachability."
requirements-completed: [DELV-06]
coverage:
  - id: D1
    description: "Every browser request is intercepted before navigation and undeclared methods, paths, external assets, or mutation bodies fail closed."
    requirement: DELV-06
    verification:
      - kind: integration
        ref: "npx playwright test --grep-invert 'visual checkpoints'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dashboard, search, title, and reconciled post-watch dashboard states each have axe and screenshot assertions in four deterministic Chromium projects."
    requirement: DELV-06
    verification:
      - kind: e2e
        ref: "npx playwright test --grep '@smoke'"
        status: pass
    human_judgment: false
duration: 45min
completed: 2026-07-21
status: complete
---

# Phase 1 Plan 08: Browser Evidence Summary

**WatchVault now has a strict, stateful Chromium reference journey across desktop/mobile and dark/light with exact mutation evidence, four clean axe checkpoints, and generation-ready visual assertions.**

## Accomplishments

- Configured exactly four deterministic Chromium projects with fixed locale, timezone, viewports, touch settings, CSS-scale screenshots, and failure-only artifacts.
- Added a fail-closed fixture that owns every same-origin API response, blocks undeclared or external traffic, validates the exact scoped watch payload, and reconciles the mutation into refreshed dashboard data.
- Proved keyboard navigation through dashboard, search, title detail, watch mutation, and updated monthly history.
- Declared 16 stable visual checkpoints without creating or accepting local baselines.

## Task Commits

1. **Task 1: Configure deterministic browser projects** - `f36d68a`
2. **Task 2: Add strict stateful API fixture** - `d635a31`
3. **Task 3: Prove accessible reference journey** - `78f9507`
4. **Stale-response race hardening** - `f633793`
5. **Permission-gate test stabilization** - `fb523ce`

## Deviations from Plan

- Axe exposed pre-existing zoom, unnamed search controls, theme contrast, and segmented-control contrast barriers. These were corrected in the same plan because clean accessibility checkpoints are a required deliverable.
- Lazy poster enrichment is an additional real journey API surface; the fixture now validates its allowlisted title IDs instead of silently bypassing it.
- Parallel validation exposed an older household request overwriting newer profile state. The shared fetch hook now ignores stale responses and has a focused race regression.
- The read-only permission test no longer waits on an unrelated profile-settling transition; scoped mutation tests still require the settled profile response.

## Issues Encountered

Mobile pointer clicks on the floating tab bar were intercepted after full-page evidence scans. Keyboard focus and Enter activation both satisfy the accessibility contract and produce stable navigation in every project.

## Next Phase Readiness

CI can now select the nonvisual smoke independently from ordinary visual comparison, while the pinned Linux generation flow can create all 16 authoritative baselines for human approval.

---
*Completed: 2026-07-21*
