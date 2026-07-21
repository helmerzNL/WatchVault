---
phase: 01-delivery-safeguards-and-behavioral-baseline
plan: "01"
subsystem: testing
tags: [node-test, version-policy, capabilities, docker, github-actions]
requires: []
provides:
  - Fail-first contracts for canonical versioning and protected-path enforcement
  - Fail-first contracts for capability inventory completeness and deterministic reporting
  - Fail-first contracts for path-aware CI, workflow semantics, and Docker version propagation
affects: [01-03, 01-04, 01-07, 01-09]
tech-stack:
  added: []
  patterns: [syntax-valid RED tests, explicit missing-artifact diagnostics, argument-array child processes]
key-files:
  created:
    - scripts/tests/assert-red.mjs
    - scripts/tests/version-policy.test.mjs
    - scripts/tests/docker-contract.test.mjs
    - scripts/tests/ci-changes.test.mjs
    - frontend/scripts/workflow-contract.test.mjs
    - frontend/scripts/capabilities.test.mjs
  modified: []
key-decisions:
  - "RED assertions require both a nonzero test exit and the exact missing production boundary."
  - "Workflow contracts check for ci.yml before importing yaml so dependency approval remains a separate gate."
patterns-established:
  - "Contract tests import stable public functions rather than reaching into implementation details."
  - "Child processes use executable-plus-argument arrays with shell execution disabled."
requirements-completed: [DELV-01, DELV-02, DELV-03, DELV-04, DELV-05, DELV-06]
coverage:
  - id: D1
    description: "Version policy and Docker delivery behavior have executable fail-first contracts."
    requirement: DELV-01
    verification:
      - kind: unit
        ref: "node scripts/tests/assert-red.mjs scripts/tests/version-policy.test.mjs scripts/lib/version-policy.mjs"
        status: pass
      - kind: unit
        ref: "node scripts/tests/assert-red.mjs scripts/tests/docker-contract.test.mjs scripts/docker-version.mjs"
        status: pass
    human_judgment: false
  - id: D2
    description: "Capability inventory validation, discovery, ordering, and report generation have executable fail-first contracts."
    requirement: DELV-05
    verification:
      - kind: unit
        ref: "node scripts/tests/assert-red.mjs frontend/scripts/capabilities.test.mjs frontend/scripts/capabilities.mjs"
        status: pass
    human_judgment: false
  - id: D3
    description: "Changed-surface selection and CI workflow semantics have executable fail-first contracts."
    requirement: DELV-06
    verification:
      - kind: unit
        ref: "node scripts/tests/assert-red.mjs scripts/tests/ci-changes.test.mjs scripts/ci-changes.mjs"
        status: pass
      - kind: unit
        ref: "node scripts/tests/assert-red.mjs frontend/scripts/workflow-contract.test.mjs .github/workflows/ci.yml"
        status: pass
    human_judgment: false
duration: 24min
completed: 2026-07-21
status: complete
---

# Phase 1 Plan 01: Fail-First Delivery Contracts Summary

**Six syntax-valid RED suites now define the delivery, inventory, Docker, and CI boundaries before production implementation begins.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-21T14:48:25Z
- **Completed:** 2026-07-21T15:12:25Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added stable public-API contracts for SemVer parsing, protected paths, synchronized records, staged checks, and idempotent bumping.
- Added strict capability inventory contracts covering schema, ownership, evidence, source anchors, discovery, ordering, and deterministic Markdown.
- Added Docker, changed-surface, and GitHub Actions contracts with exact missing-artifact RED diagnostics.

## Task Commits

1. **Task 1: Delivery version and Docker fail-first contracts** - `e8f2575`
2. **Task 2: Capability inventory fail-first contracts** - `0a7a768`
3. **Task 3: CI selection and workflow fail-first contracts** - `0f66f3c`

## Files Created/Modified

- `scripts/tests/assert-red.mjs` - Verifies syntax-valid tests fail for one expected production boundary.
- `scripts/tests/version-policy.test.mjs` - Defines canonical version, policy, synchronization, CLI, and hook behavior.
- `scripts/tests/docker-contract.test.mjs` - Defines image, Compose, adapter, and documentation version propagation.
- `scripts/tests/ci-changes.test.mjs` - Defines the path-to-job selection matrix and fail-closed behavior.
- `frontend/scripts/workflow-contract.test.mjs` - Defines CI provisioning, security, gate, generation, and publication semantics.
- `frontend/scripts/capabilities.test.mjs` - Defines strict inventory validation, discovery, ordering, and generation behavior.

## Decisions Made

- Public test contracts use named exports that later implementations must satisfy.
- RED verification is centralized so an unrelated syntax error cannot masquerade as a valid fail-first result.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-03, 01-04, 01-07, and 01-09 now have executable contracts to turn green. Plan 01-02 remains the blocking dependency-legitimacy checkpoint before frontend packages can be installed.

---
*Phase: 01-delivery-safeguards-and-behavioral-baseline*
*Completed: 2026-07-21*
