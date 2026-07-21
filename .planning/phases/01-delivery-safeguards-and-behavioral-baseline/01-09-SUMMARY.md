---
phase: 01-delivery-safeguards-and-behavioral-baseline
plan: "09"
subsystem: delivery-ci
tags: [github-actions, path-selection, aggregate-gate, playwright, ghcr]
requires:
  - phase: 01-delivery-safeguards-and-behavioral-baseline
    provides: Canonical version policy, capability inventory, test harnesses, and browser evidence
provides:
  - Fail-closed changed-surface selection with always-on version and inventory checks
  - Stable aggregate delivery gate with explicit selected and skipped job semantics
  - Dispatch-only 16-image Linux baseline artifact with SHA-256 manifest
  - Reusable Docker publisher gated by successful delivery validation
affects: [01-10, 09-tagged-release-and-operational-readiness]
tech-stack:
  added: []
  patterns: [pure path classifier, argument-array Git adapter, needs-result aggregation, reusable publisher]
key-files:
  created: [.github/workflows/ci.yml, scripts/ci-changes.mjs, scripts/ci/aggregate.mjs, scripts/tests/ci-aggregate.test.mjs]
  modified: [.github/workflows/docker.yml, frontend/package.json]
key-decisions:
  - "Pull requests always run version and capability contracts while heavy jobs are selected from normalized changed paths."
  - "Unknown safe repository surfaces select the full suite; unsafe paths, refs, and events fail before emitting outputs."
  - "The aggregate gate accepts skipped heavy jobs only when selector outputs explicitly mark them unselected."
  - "Only dispatch generation may update snapshots; ordinary browser CI runs the full nonvisual @smoke journey."
requirements-completed: [DELV-06]
coverage:
  - id: D1
    description: "Every CI path emits one stable aggregate result, and selected failures or contradictory skips fail it."
    requirement: DELV-06
    verification:
      - kind: contract
        ref: "npm --prefix frontend run test:contracts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Docker publication is reusable, package-write scoped, gate-dependent, and receives canonical VERSION through the adapter."
    requirement: DELV-01
    verification:
      - kind: contract
        ref: "frontend/scripts/workflow-contract.test.mjs"
        status: pass
    human_judgment: false
duration: 11min
completed: 2026-07-21
status: complete
---

# Phase 1 Plan 09: CI Integration Summary

**WatchVault now has path-aware clean-runner CI, one fail-closed `delivery / gate`, dispatch-only manifest-backed baseline generation, and Docker publication that cannot run before validation succeeds.**

## Accomplishments

- Added a pure normalized path classifier plus a safe GitHub-output adapter using argument-array Git execution and full-SHA validation.
- Provisioned Node 20.19.x, Python 3.12, locked frontend dependencies, backend requirements, and pinned Playwright 1.61.1 jobs on clean runners.
- Added contract, version, inventory, backend, frontend, browser smoke, and baseline-generation jobs with explicit selection and skip behavior.
- Added an aggregate script and focused tests that reject failures, missing jobs, malformed outputs, and unexplained skips.
- Converted Docker publication into a reusable workflow with canonical VERSION build args and OCI metadata while preserving Buildx metadata and GHA caches.

## Task Commits

1. **Task 1: Implement fail-closed job selection** - `da13faa`
2. **Task 2: Add selective delivery workflow and aggregate gate** - `cecf72b`
3. **Task 3: Gate reusable Docker publication** - `8fbbf92`

## Deviations from Plan

- Added focused aggregate-gate tests to the explicit contract suite so skip/failure semantics are executable rather than only represented in workflow YAML.
- Local Plan 01-09 validation ran the exact nonvisual browser smoke used by CI. The full screenshot comparison remains intentionally deferred until Plan 01-10 imports and approves the authoritative Linux artifact.

## Issues Encountered

PowerShell interpreted the unquoted `@smoke` argument through the npm wrapper. Re-running through `npm.cmd` passed the literal Playwright tag and all four browser projects succeeded.

## Next Phase Readiness

Plan 01-10 can begin after this workflow is available on GitHub: dispatch baseline generation, verify and review all 16 images, then configure the exact `delivery / gate` repository ruleset without bypass.

---
*Completed: 2026-07-21*
