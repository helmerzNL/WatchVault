# Requirements: WatchVault Cinematic Redesign

**Defined:** 2026-07-21
**Core Value:** Self-hosting media enthusiasts can move effortlessly from their dashboard to finding a title, understanding its details, and maintaining accurate personal or household watch history.

## User Stories

- As a household member, I can understand my current viewing activity immediately and move into the title or history action I need without learning the application structure.
- As a media enthusiast, I can search, inspect, and correct detailed watch data through an artwork-led interface that remains fast and legible.
- As a mobile PWA user, I can use every relevant WatchVault capability without falling back to a desktop layout or pointer-only interaction.
- As an administrator, I can manage profiles, sources, integrations, repair workflows, and destructive operations through a clear permission-aware information architecture.
- As a keyboard or assistive-technology user, I can navigate and operate the complete application with visible focus, semantic feedback, and accessible alternatives to visual charts.
- As a self-hoster, I can identify, deploy, update, roll back, back up, and restore a reproducible versioned release safely.

## v1 Requirements

### Delivery Safeguards

- [ ] **DELV-01**: Maintainer can identify one canonical SemVer project version used consistently by the application, build, image metadata, and release tag
- [ ] **DELV-02**: Contributor receives a blocking CI error with the exact remediation command when protected runtime, build, deploy, script, or workflow paths change without a required version bump
- [ ] **DELV-03**: Contributor can run an idempotent helper that bumps the project version only when the protected-path policy requires it
- [ ] **DELV-04**: Contributor gets fast pre-commit enforcement through a repository-configured `core.hooksPath`, while heavyweight checks remain in CI
- [ ] **DELV-05**: Maintainer can review a capability inventory mapping every existing route, action, permission, scope, preference, locale, theme, and important UI state to redesign acceptance coverage
- [ ] **DELV-06**: CI runs the existing backend suite plus frontend type, component, accessibility, visual, and critical-journey regression checks required by changed surfaces

### Design System

- [ ] **DSYS-01**: User sees a cohesive cinematic interface driven by semantic tokens for color, typography, spacing, radii, elevation, opacity, motion, and responsive breakpoints
- [ ] **DSYS-02**: User can use consistent buttons, fields, selects, menus, tabs, dialogs, cards, badges, tooltips, toasts, tables, and chart controls across all screens
- [ ] **DSYS-03**: User receives consistent hover, active, focus, selected, disabled, busy, success, warning, and error feedback from reusable interaction primitives
- [ ] **DSYS-04**: User sees posters and backdrops through one artwork system with stable aspect ratios, responsive sources, lazy loading, scrims, focal treatment, and meaningful fallbacks
- [ ] **DSYS-05**: User can use the interface in dark, light, or system mode with deliberate token, chart, artwork-overlay, focus, loading, and error-state parity
- [ ] **DSYS-06**: User who prefers reduced motion receives an equivalent experience without parallax, large scale or pan effects, or nonessential looping animation
- [ ] **DSYS-07**: Contributor can inspect reusable components and their responsive, theme, locale, interaction, loading, empty, and error states in an isolated component workshop

### Navigation and Scope

- [ ] **SHEL-01**: User can navigate all permitted destinations through one adaptive shell with equivalent desktop and mobile information architecture
- [ ] **SHEL-02**: User can always identify the active route and recover predictably through browser history, deep links, page titles, and contextual back or breadcrumb behavior
- [ ] **SHEL-03**: User can see and intentionally change the active personal or household scope without that scope silently resetting
- [ ] **SHEL-04**: User sees navigation and actions appropriate to current permissions while direct access to forbidden operations returns a clear forbidden state
- [ ] **SHEL-05**: Keyboard user can bypass repeated navigation, traverse landmarks in logical order, and retain meaningful focus after route and dialog transitions
- [ ] **SHEL-06**: Installed PWA user receives safe-area-aware navigation and content on narrow, wide, portrait, and landscape viewports

### Reference Journey

- [ ] **DASH-01**: User can understand now playing, totals, trends, recent activity, unfinished items, unknown items, and relevant alerts from a clear dashboard hierarchy
- [ ] **DASH-02**: User can personalize supported dashboard modules through bounded show, hide, reorder, and restore-default actions with a keyboard-operable alternative
- [ ] **DASH-03**: User with no or partial data sees a dashboard state that explains the situation and links to the most relevant import, connection, or manual-history action
- [ ] **DASH-04**: User can move from a dashboard module into the correctly scoped title, person, history, statistics, source, or repair context
- [ ] **SRCH-01**: User can start global search quickly and refine results by existing title, person, genre, provider, platform, year, kind, and tag dimensions
- [ ] **SRCH-02**: User can see active search constraints, remove one constraint, clear all constraints, and preserve meaningful filter state through navigation
- [ ] **SRCH-03**: Keyboard and screen-reader user can operate suggestions, facets, result navigation, loading feedback, and result-count announcements
- [ ] **SRCH-04**: User can scan responsive search results with stable artwork, essential metadata, complete actions, and explicit progressive loading
- [ ] **TITL-01**: User can identify a title through an artwork-led overview containing available kind, release information, network or provider, genres, description, and metadata status
- [ ] **TITL-02**: User can understand watched state, total time, episode progress, unfinished progress, last position, now-playing status, and active scope without calculation
- [ ] **TITL-03**: User can navigate seasons, specials, episodes, cast, crew, people, genres, and related existing catalog relationships at desktop and mobile sizes
- [ ] **TITL-04**: Authorized user can complete every existing title and episode action, including adding or removing watches, marking watched, season actions, manual overrides, enrichment, synchronization, and attribution
- [ ] **TITL-05**: User receives usable title-detail states when metadata, artwork, enrichment, episode information, or provider identity is incomplete
- [ ] **HIST-01**: User can review watch history as a scoped ledger showing date and time, title or episode, profile, provider or source, and relevant attribution context
- [ ] **HIST-02**: Authorized user can add, edit, and remove history records with input validation, pending state, clear consequences, success or error feedback, and server reconciliation
- [ ] **HIST-03**: User sees dashboard, progress, aggregates, and statistics reconcile after a successful history mutation without requiring a full application reload

### Catalog and Analytics

- [ ] **ANLY-01**: User can browse and drill through all existing overview, title, person, genre, network, platform, and unknown-item catalog surfaces
- [ ] **ANLY-02**: User can view all existing statistics with consistent profile or household scope, year or range selection, and time granularity controls
- [ ] **ANLY-03**: User can understand chart meaning through labels, summaries, tooltips, non-color distinctions, and keyboard or table alternatives where interaction is required
- [ ] **ANLY-04**: User sees responsive analytical layouts that preserve values, legends, controls, and drill-down actions without horizontal page overflow
- [ ] **ANLY-05**: User receives distinct loading, empty-range, filtered-empty, partial-data, error, and stale-data treatment for catalog and analytical surfaces

### Household and Administration

- [ ] **ADMN-01**: User can navigate settings through clear Personal, Appearance, Household, Profiles, Sources and Imports, Integrations, Advanced, and Danger Zone groupings
- [ ] **ADMN-02**: User can manage existing language, theme, accent, default profile, dashboard, and expert-mode preferences with immediate and reversible feedback
- [ ] **ADMN-03**: Authorized user can create, edit, remove, recover, and administer household profiles and roles without losing existing permission safeguards
- [ ] **ADMN-04**: Authorized user can import files and add, configure, authorize, synchronize, map, inspect, and remove all existing provider connections and libraries
- [ ] **ADMN-05**: Authorized user can understand normalized connection health, last synchronization, queued or running work, stale state, actionable failure, and safe retry behavior
- [ ] **ADMN-06**: Authorized user can manage existing plugins, credentials, API tokens, tags, scrobble endpoints, thresholds, and account mappings without exposing secret values
- [ ] **ADMN-07**: Authorized user can use existing attribution, unknown-title, metadata-override, bulk-platform, re-attribution, rebuild, and repair workflows with audit-oriented feedback
- [ ] **ADMN-08**: User sees destructive profile, source, catalog, reset, and bulk actions isolated in a danger treatment with consequence copy, permission checks, confirmation, and busy-state protection

### Cross-App Quality

- [ ] **QUAL-01**: User can operate every redesigned route and action at 320 CSS pixels, at 200% zoom, in portrait and landscape, and with content reflow instead of two-dimensional page scrolling
- [ ] **QUAL-02**: Keyboard user can reach and operate every interactive element with logical order, visible unobscured focus, no traps, and explicit alternatives to hover, drag, swipe, and long-press
- [ ] **QUAL-03**: Screen-reader user receives semantic landmarks, heading order, labels, names, roles, values, dialog focus management, and live status for search, save, sync, and errors
- [ ] **QUAL-04**: User can read text and perceive required controls and graphical cues at WCAG AA contrast in both themes and across representative artwork
- [ ] **QUAL-05**: User receives complete layouts in every existing supported locale with text expansion, no hard-coded interface strings, and defined metadata fallback behavior
- [ ] **QUAL-06**: User receives clear route, section, image, refresh, and action loading states without blocking already usable content unnecessarily
- [ ] **QUAL-07**: User receives distinct first-use, no-result, filtered-empty, no-permission, missing-configuration, recoverable-error, offline, and stale-data states with relevant next actions
- [ ] **QUAL-08**: Authenticated API responses and personalized data are not reused across logout, account change, or profile or household scope change through service-worker or client caches
- [ ] **QUAL-09**: Mobile user receives artwork and route performance within defined budgets through responsive images, route splitting, bounded caches, and measured loading priorities
- [ ] **QUAL-10**: Maintainer can verify every capability-inventory entry across required permissions, themes, locales, viewports, PWA modes, loading states, and failure states before removing legacy UI

### Release and Operations

- [ ] **RELS-01**: Release workflow publishes only from a matching `vX.Y.Z` tag after required build, test, accessibility, visual, security, version, and secret gates pass
- [ ] **RELS-02**: Maintainer can reproduce release artifacts from locked source and dependency inputs and identify the immutable image digest, provenance, and software bill of materials
- [ ] **RELS-03**: Maintainer can apply documented stable, latest, and beta channel rules without silently replacing an immutable released version
- [ ] **RELS-04**: Public release contains no committed `.env` files or live credentials, provides only safe placeholders in `.env.example`, and documents required secret rotation
- [ ] **RELS-05**: Self-hoster can follow the README to set up, run, stop, health-check, deploy, update, roll back, back up, and restore WatchVault and locate its runtime components and persistent data
- [ ] **RELS-06**: Maintainer can demonstrate a clean-host install plus update, rollback, backup, and restore rehearsal before declaring the redesign release complete

## Acceptance Criteria

- Every v1 requirement is mapped to exactly one roadmap phase and has automated or explicit manual verification evidence.
- Every existing user-facing route and operation is represented in the capability inventory and passes parity review before legacy UI removal.
- The dashboard → search → title detail → watch-history journey passes in dark and light themes across desktop and mobile projects with keyboard and accessibility checks.
- No authenticated data survives logout or identity or scope changes through frontend or service-worker caches.
- The final release is versioned, reproducible, tag-driven, secret-safe, operationally documented, and recoverable.

## Definition of Done

- All v1 requirements are implemented and verified.
- Backend, frontend, accessibility, visual, PWA, and critical end-to-end checks pass in CI.
- Required SemVer bump and protected-path enforcement pass locally and in CI.
- Capability parity is signed off for permissions, themes, locales, viewports, states, and existing operations.
- A matching `vX.Y.Z` release artifact is reproducible and the documented deployment, rollback, backup, and restore procedures have been rehearsed.

## v2 Requirements

Deferred beyond the redesign milestone.

### Product Expansion

- **V2-01**: User can receive personalized title recommendations
- **V2-02**: User can use social feeds, follows, comments, public profiles, ratings, or reviews
- **V2-03**: User can use net-new watchlists, release calendars, notifications, or streaming-availability discovery
- **V2-04**: User can install a native iOS or Android application

### Platform Evolution

- **V2-05**: Maintainer can migrate the application to React 19, React Router 7, or Recharts 3 in a separately validated milestone
- **V2-06**: Maintainer can adopt generated OpenAPI clients or broadly refactor the Flask backend in a separately scoped milestone

## Out of Scope

| Feature | Reason |
|---------|--------|
| Recommendation engine | Expands the product into a new algorithmic domain rather than improving current capabilities |
| Social network features | Conflicts with WatchVault's private self-hosted household position and adds moderation and privacy scope |
| Native mobile apps | The responsive installable PWA remains the single client |
| Net-new watchlists, calendars, notifications, or availability discovery | Competitor features are not part of the current capability-preserving redesign |
| Arbitrary dashboard widget platform | Bounded personalization preserves accessibility and maintainability |
| Autoplay video heroes, parallax, or gesture-only controls | These undermine performance, reduced-motion support, and input accessibility |
| Broad backend or framework migration | Combining platform migration with a full redesign would increase risk without serving the milestone's core value |
| Copying competitor branding or layouts | WatchVault should apply proven principles through its own identity and interaction system |

## Traceability

Roadmap phase mapping is populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|

**Coverage:**
- v1 requirements: 64 total
- Mapped to phases: 0
- Unmapped: 64

---
*Requirements defined: 2026-07-21*
*Last updated: 2026-07-21 after initial definition*
