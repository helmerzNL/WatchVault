# Phase 1: Delivery Safeguards and Behavioral Baseline - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the enforceable delivery foundation for the redesign: one canonical project version, protected-path version enforcement, fast repository hooks, a complete inventory of existing capabilities, and automated regression evidence. This phase is limited to DELV-01 through DELV-06 and does not redesign product screens.

</domain>

<decisions>
## Implementation Decisions

### Canonical version source and synchronization
- **D-01:** A plain root `VERSION` file is the single source of truth for the full product.
- **D-02:** The version helper synchronizes `frontend/package.json` and `frontend/package-lock.json`; the Docker image embeds OCI version labels; backend metadata exposes the version; CI verifies matching `vX.Y.Z` release tags.
- **D-03:** The helper compares protected changes with the merge base, defaults to a patch bump only when needed, becomes a no-op after a sufficient bump, and accepts explicit `--minor` and `--major` overrides.
- **D-04:** Phase 1 adopts the existing `1.0.0` package version as its baseline and leaves the repository at `1.0.1`.

### Protected-path policy and remediation
- **D-05:** Version-protected paths are `backend/**`, `frontend/**`, `plugins/**`, `homeassistant/**`, `deploy/**`, `scripts/**`, `Dockerfile`, compose files, and `.github/workflows/**`.
- **D-06:** One machine-readable root policy file owns include and exclude rules; CI, the helper, and the hook consume this same policy rather than duplicating path lists.
- **D-07:** Every version-policy failure prints the exact remediation command `node scripts/version.mjs bump`; the same command supports `--minor` and `--major`.
- **D-08:** The pre-commit hook blocks staged protected changes without a sufficient staged version bump and blocks synchronized-version drift. It does not run builds or test suites.
- **D-09:** Repository setup configures `core.hooksPath` to the committed hooks directory so local enforcement is active through repository configuration.

### Capability inventory structure and ownership
- **D-10:** Machine-readable JSON is the canonical capability inventory, with a generated Markdown report for human review.
- **D-11:** Inventory entries use stable atomic IDs. A distinct entry represents each route, action, permission rule, scope behavior, preference, locale or theme obligation, and important UI state.
- **D-12:** Every entry records its source location, current behavior, applicable permission/scope/theme/locale/state dimensions, owning roadmap requirement and phase, and planned or existing regression evidence.
- **D-13:** CI blocks invalid schemas, duplicate IDs, invalid source or requirement references, stale generated Markdown, and gaps in discoverable route, locale, theme, or preference catalogs.
- **D-14:** Existing capabilities cannot be silently deferred or omitted; all current behavior must have explicit redesign ownership.

### Regression gates and local-check boundaries
- **D-15:** Backend regression coverage remains on pytest. Frontend coverage uses Vitest, Testing Library, and axe for component/accessibility checks, plus Playwright for browser journeys and visual snapshots.
- **D-16:** Initial Playwright journeys use deterministic browser-level API fixtures to exercise the real React application and routing; backend behavior remains independently covered by pytest.
- **D-17:** The blocking browser baseline uses pinned Chromium at desktop and mobile sizes and captures both dark and light states across the dashboard-to-search-to-title-to-history reference journey.
- **D-18:** Version and inventory validation always run in CI. Pull requests use changed paths to select backend, frontend, and browser jobs; pushes to `main` and release tags run the complete suite.
- **D-19:** Heavy type, component, accessibility, visual, journey, and backend checks remain in CI rather than the pre-commit hook.

### the agent's Discretion
- Exact filenames and JSON schemas for the version policy and capability inventory.
- Exact repository setup command or bootstrap script that applies `core.hooksPath`.
- Snapshot thresholds, artifact names, and CI retention periods, provided intentional updates are reviewable and the pinned browser baseline remains deterministic.
- Exact component fixtures and Playwright fixture organization.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and delivery constraints
- `.planning/REQUIREMENTS.md` §Delivery Safeguards — Defines DELV-01 through DELV-06.
- `.planning/ROADMAP.md` §Phase 1 — Defines the fixed phase goal and success criteria.
- `.planning/PROJECT.md` §Constraints — Defines mandatory SemVer, CI, hooks, secrets, release, and operational rules.

### Existing validation and repository structure
- `.planning/codebase/TESTING.md` — Documents the 153-test pytest baseline, missing frontend runner, and current CI gaps.
- `.planning/codebase/STRUCTURE.md` — Maps protected runtime/build/deploy surfaces and their integration points.
- `.planning/codebase/CONVENTIONS.md` — Defines existing test, TypeScript build, error-handling, and repository conventions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/tests/`: Existing pytest behavior suite and handwritten fake patterns provide the backend baseline.
- `frontend/package.json`: Existing `1.0.0` value provides the version baseline and the manifest scripts surface for new frontend checks.
- `frontend/src/lib/api.ts` and `frontend/src/lib/useFetch.ts`: Stable network boundaries for deterministic component and browser fixtures.
- `frontend/src/lib/app.tsx`: Central theme, profile, scope, permission, and preference state to enumerate in the capability inventory.

### Established Patterns
- Frontend validation currently uses `npm run build`, which performs `tsc -b` before Vite.
- Backend tests are DB- and network-independent, using pytest `monkeypatch` and handwritten fakes.
- `.github/workflows/docker.yml` already derives image tags from refs and emits `latest` for the default branch, but it does not verify a canonical project version.
- `docker-compose.yml` currently consumes `ghcr.io/helmerznl/watchvault:latest`.
- No committed scripts directory, git-hook directory, frontend test runner, or browser suite currently exists.

### Integration Points
- `backend/app/api/meta.py`: Expose the canonical runtime version through existing metadata/health behavior.
- `Dockerfile`: Read `VERSION` and apply OCI image metadata.
- `.github/workflows/docker.yml`: Verify version/tag agreement and integrate release metadata.
- A new root policy plus `scripts/version.mjs`: Shared version-policy engine for CI and hooks.
- `frontend/src/App.tsx`, backend blueprint registration, locale modules, theme/preference state, and permission checks: Discoverable sources for capability-inventory validation.

</code_context>

<specifics>
## Specific Ideas

- The exact contributor recovery path is `node scripts/version.mjs bump`.
- The browser baseline follows the approved reference journey: dashboard, search, title detail, then watch-history mutation.
- Desktop/mobile and dark/light are required baseline dimensions from the start rather than deferred expansions.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-delivery-safeguards-and-behavioral-baseline*
*Context gathered: 2026-07-21*
