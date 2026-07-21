# Roadmap: WatchVault Cinematic Redesign

## Overview

WatchVault's redesign proceeds through nine dependency-driven phases. Delivery safeguards and a capability baseline protect the existing product before typed client data and PWA cache safety are established. A cinematic design system then enables an adaptive shell, followed by the reference dashboard-to-history journey, remaining catalog and administrative surfaces, integrated quality hardening, and a reproducible operational release.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Delivery Safeguards and Behavioral Baseline** - Make redesign changes measurable, versioned, and protected against capability regressions.
- [ ] **Phase 2: Typed Data and PWA State Safety** - Prevent authenticated or scoped data from surviving identity and scope transitions.
- [ ] **Phase 3: Cinematic Design System** - Give every redesigned surface shared visual, interaction, artwork, theme, and motion foundations.
- [ ] **Phase 4: Adaptive Shell and Global Scope** - Provide one accessible, permission-aware navigation frame across desktop and installed mobile use.
- [ ] **Phase 5: Reference Journey** - Deliver the complete dashboard, search, title-detail, and watch-history journey at reference quality.
- [ ] **Phase 6: Catalog and Analytics** - Extend the proven media and data patterns across all catalog and statistics surfaces.
- [ ] **Phase 7: Household and Administration** - Make preferences, profiles, sources, integrations, repair, and destructive operations clear and safe.
- [ ] **Phase 8: Cross-App Hardening and Legacy Removal** - Verify every redesigned capability across accessibility, responsive, locale, state, and performance conditions.
- [ ] **Phase 9: Tagged Release and Operational Readiness** - Ship a reproducible, secret-safe release that self-hosters can operate and recover.

## Phase Details

### Phase 1: Delivery Safeguards and Behavioral Baseline

**Goal**: Maintainers and contributors can change the redesign with enforceable versioning, complete capability coverage, and regression evidence.
**Depends on**: Nothing (first phase)
**Requirements**: DELV-01, DELV-02, DELV-03, DELV-04, DELV-05, DELV-06
**Success Criteria** (what must be TRUE):

  1. Maintainer can identify one canonical SemVer value that agrees across the application, build, image metadata, and release tag.
  2. Contributor changing a protected path without a required bump receives a blocking error with the exact remediation command, and the idempotent helper resolves only required bumps.
  3. Contributor receives fast repository-configured pre-commit feedback while CI retains the heavyweight backend and frontend regression gates.
  4. Maintainer can inspect an acceptance inventory covering every existing route, action, permission, scope, preference, locale, theme, and important UI state.
  5. CI blocks relevant backend, type, component, accessibility, visual, or critical-journey regressions before redesigned surfaces proceed.

**Plans:** 8/10 plans executed
**Wave 0**

- [x] 01-01-PLAN.md — Create Wave 0 fail-first contracts for delivery policy and capability coverage.
- [x] 01-02-PLAN.md — Approve the exact frontend test stack through the blocking supply-chain gate.

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 01-03-PLAN.md — Implement canonical version policy, CLI behavior, and synchronized manifests.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-04-PLAN.md — Wire canonical versioning into runtime, image builds, Compose, and local hooks.
- [x] 01-05-PLAN.md — Install the approved test stack and create reusable frontend test infrastructure.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-06-PLAN.md — Add representative component and DOM-accessibility regression evidence.
- [x] 01-07-PLAN.md — Create and populate the strict capability inventory and generated report.
- [x] 01-08-PLAN.md — Add deterministic Chromium journey, accessibility, and visual regression evidence.

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-09-PLAN.md — Integrate path-aware CI, the aggregate gate, baseline generation, and gated publication.

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 01-10-PLAN.md — Approve authoritative baselines and configure the repository-required aggregate check.

### Phase 2: Typed Data and PWA State Safety

**Goal**: Users never receive personalized data from a previous identity or personal/household scope through client or service-worker caches.
**Depends on**: Phase 1
**Requirements**: QUAL-08
**Success Criteria** (what must be TRUE):

  1. After logout or account change, the browser and installed PWA cannot display authenticated API responses from the previous account, including while offline.
  2. After personal or household scope changes, data from the previous scope is not reused by client or service-worker caches.
  3. Refreshing or reconnecting after an identity or scope transition resolves only data belonging to the current authenticated context.

**Plans**: TBD

### Phase 3: Cinematic Design System

**Goal**: Users experience one cohesive, accessible cinematic language through reusable components in every supported theme and motion preference.
**Depends on**: Phase 2
**Requirements**: DSYS-01, DSYS-02, DSYS-03, DSYS-04, DSYS-05, DSYS-06, DSYS-07
**Success Criteria** (what must be TRUE):

  1. User sees consistent semantic color, type, spacing, shape, elevation, opacity, motion, breakpoint, control, and interaction-state treatment.
  2. User sees stable responsive posters and backdrops with appropriate loading, scrims, focal treatment, and meaningful fallbacks.
  3. User can select dark, light, or system mode and receives equivalent controls, charts, artwork overlays, focus, loading, and error states.
  4. User who prefers reduced motion receives an equivalent experience without nonessential parallax, scale, pan, or looping animation.
  5. Contributor can inspect reusable components across responsive, theme, locale, interaction, loading, empty, and error states in isolation.

**Plans**: TBD
**UI hint**: yes

### Phase 4: Adaptive Shell and Global Scope

**Goal**: Users can orient, navigate, and maintain explicit scope through one adaptive, accessible, permission-aware application shell.
**Depends on**: Phase 3
**Requirements**: SHEL-01, SHEL-02, SHEL-03, SHEL-04, SHEL-05, SHEL-06
**Success Criteria** (what must be TRUE):

  1. User can reach every permitted destination through equivalent desktop and mobile navigation and can always identify the active route.
  2. Browser history, deep links, page titles, and contextual back or breadcrumb behavior return users to predictable locations.
  3. User can see and intentionally change personal or household scope without it silently resetting.
  4. User sees only navigation and actions allowed by current permissions, while direct forbidden access produces a clear forbidden state.
  5. Keyboard and installed-PWA users receive skip navigation, logical landmarks, meaningful transition focus, and safe-area-aware layouts in narrow, wide, portrait, and landscape views.

**Plans**: TBD
**UI hint**: yes

### Phase 5: Reference Journey

**Goal**: Users can move confidently from dashboard to search, title understanding, and accurate watch-history maintenance.
**Depends on**: Phase 4
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, SRCH-01, SRCH-02, SRCH-03, SRCH-04, TITL-01, TITL-02, TITL-03, TITL-04, TITL-05, HIST-01, HIST-02, HIST-03
**Success Criteria** (what must be TRUE):

  1. User can understand and personalize the scoped dashboard, recover from no or partial data, and follow each module into the correct title, person, history, statistics, source, or repair context.
  2. User can quickly search by all supported dimensions, understand and revise active constraints, preserve filter state, and operate suggestions and progressive results with keyboard or screen reader.
  3. User can understand a title's identity, metadata, watched and now-playing state, progress, seasons, episodes, people, genres, and related catalog data across desktop and mobile, including incomplete-data states.
  4. Authorized user can complete every existing title and episode watch, override, enrichment, synchronization, season, and attribution action with clear state and permission feedback.
  5. User can review the scoped history ledger and safely add, edit, or remove records, after which dashboard, progress, aggregates, and statistics reconcile without a full reload.

**Plans**: TBD
**UI hint**: yes

### Phase 6: Catalog and Analytics

**Goal**: Users can traverse the complete catalog and understand scoped statistics through responsive and accessible analytical views.
**Depends on**: Phase 5
**Requirements**: ANLY-01, ANLY-02, ANLY-03, ANLY-04, ANLY-05
**Success Criteria** (what must be TRUE):

  1. User can browse and drill through every existing overview, title, person, genre, network, platform, and unknown-item catalog view.
  2. User can view every existing statistic with consistent personal or household scope, year or range selection, and time-granularity controls.
  3. User can understand chart values through labels, summaries, tooltips, non-color distinctions, and keyboard or table alternatives.
  4. User retains values, legends, controls, and drill-down actions without horizontal page overflow and receives distinct loading, empty, partial, error, and stale states.

**Plans**: TBD
**UI hint**: yes

### Phase 7: Household and Administration

**Goal**: Users can manage preferences, household data, integrations, repairs, and dangerous operations through clear permission-aware workflows.
**Depends on**: Phase 6
**Requirements**: ADMN-01, ADMN-02, ADMN-03, ADMN-04, ADMN-05, ADMN-06, ADMN-07, ADMN-08
**Success Criteria** (what must be TRUE):

  1. User can navigate clearly grouped settings and change language, appearance, default profile, dashboard, and expert-mode preferences with immediate reversible feedback.
  2. Authorized user can create, edit, remove, recover, and administer household profiles and roles without bypassing permission safeguards.
  3. Authorized user can import data and configure, authorize, synchronize, map, inspect, retry, and remove provider connections while understanding health, freshness, progress, and failures.
  4. Authorized user can manage plugins, credentials, API tokens, tags, scrobble endpoints, thresholds, and account mappings without secret values being exposed.
  5. Authorized user can complete attribution, unknown-title, metadata, bulk-platform, rebuild, repair, reset, and other destructive workflows with audit-oriented consequences, confirmation, permission, and busy-state protection.

**Plans**: TBD
**UI hint**: yes

### Phase 8: Cross-App Hardening and Legacy Removal

**Goal**: Users receive complete, accessible, localized, resilient, and performant behavior on every redesigned route before legacy UI is removed.
**Depends on**: Phase 7
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-09, QUAL-10
**Success Criteria** (what must be TRUE):

  1. User can operate every redesigned route at 320 CSS pixels, 200% zoom, portrait, and landscape with content reflow rather than two-dimensional page scrolling.
  2. Keyboard and screen-reader users can operate every action with logical focus, semantic structure, status announcements, dialog focus management, and explicit alternatives to pointer-only interaction.
  3. User receives WCAG AA text, control, focus, and graphical contrast in both themes over representative artwork, with complete expanded layouts in every supported locale.
  4. User receives distinct, actionable loading, refreshing, first-use, empty, forbidden, missing-configuration, error, offline, and stale states without usable content being blocked unnecessarily.
  5. Mobile artwork and route loading stay within defined budgets, and maintainers can verify every capability across required permissions, themes, locales, viewports, PWA modes, and failure states before removing legacy UI.

**Plans**: TBD
**UI hint**: yes

### Phase 9: Tagged Release and Operational Readiness

**Goal**: Self-hosters can deploy and recover a uniquely identifiable, reproducible, verified WatchVault redesign release.
**Depends on**: Phase 8
**Requirements**: RELS-01, RELS-02, RELS-03, RELS-04, RELS-05, RELS-06
**Success Criteria** (what must be TRUE):

  1. Release workflow publishes only a matching `vX.Y.Z` tag after required build, test, accessibility, visual, security, version, and secret gates pass.
  2. Maintainer can reproduce artifacts from locked inputs and identify immutable image digest, provenance, SBOM, and stable/latest/beta channel behavior without replacing immutable versions.
  3. Public release contains no committed environment or live credential data, provides safe placeholders, and identifies required secret rotation.
  4. Self-hoster can follow the README on a clean host to set up, run, stop, health-check, deploy, update, roll back, back up, and restore WatchVault and locate runtime components and persistent data.
  5. Maintainer can demonstrate clean installation plus update, rollback, backup, and restore rehearsal before declaring the redesign complete.

**Plans**: TBD

## Requirement Coverage

All 64 v1 requirements are mapped exactly once across Phases 1-9. No v1 requirement is duplicated or unmapped.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Delivery Safeguards and Behavioral Baseline | 8/10 | In Progress | - |
| 2. Typed Data and PWA State Safety | 0/TBD | Not started | - |
| 3. Cinematic Design System | 0/TBD | Not started | - |
| 4. Adaptive Shell and Global Scope | 0/TBD | Not started | - |
| 5. Reference Journey | 0/TBD | Not started | - |
| 6. Catalog and Analytics | 0/TBD | Not started | - |
| 7. Household and Administration | 0/TBD | Not started | - |
| 8. Cross-App Hardening and Legacy Removal | 0/TBD | Not started | - |
| 9. Tagged Release and Operational Readiness | 0/TBD | Not started | - |
