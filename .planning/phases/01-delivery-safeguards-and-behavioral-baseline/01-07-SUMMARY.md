---
phase: 01-delivery-safeguards-and-behavioral-baseline
plan: "07"
subsystem: capability-inventory
tags: [json-schema, ajv, typescript-compiler-api, discovery, documentation]
requires:
  - phase: 01-delivery-safeguards-and-behavioral-baseline
    provides: Fail-first inventory contract and approved Ajv/TypeScript stack
provides:
  - Strict capability schema with collected validation errors
  - Compiler-backed discovery for current routes, actions, and frontend catalogs
  - Canonical 112-record capability baseline with exact discovery parity
  - Deterministic generated Markdown review report
affects: [01-08, 01-09, 08-cross-app-hardening-and-legacy-removal]
tech-stack:
  added: []
  patterns: [compiler-api discovery, exact set reconciliation, generated-report drift checks]
key-files:
  created: [capabilities/schema.json, capabilities/inventory.json, frontend/scripts/capabilities.mjs, docs/CAPABILITIES.md]
  modified: [frontend/scripts/capabilities.test.mjs]
key-decisions:
  - "Mutating API method and normalized endpoint define one atomic action candidate."
  - "Canonical inventory order is phase, requirement, kind, then stable ID."
  - "Generated Markdown is review output only; canonical JSON remains authoritative."
requirements-completed: [DELV-05]
coverage:
  - id: D1
    description: "Schema, references, paths, anchors, ownership, uniqueness, ordering, discovery parity, and report freshness fail closed."
    requirement: DELV-05
    verification:
      - kind: unit
        ref: "node --test frontend/scripts/capabilities.test.mjs"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every discovered current route, mutation, permission, scope, preference, locale, theme, and important state has an owned canonical record."
    requirement: DELV-05
    verification:
      - kind: integration
        ref: "node frontend/scripts/capabilities.mjs check"
        status: pass
    human_judgment: false
duration: 20min
completed: 2026-07-21
status: complete
---

# Phase 1 Plan 07: Capability Inventory Summary

**WatchVault now has a strict, source-anchored 112-record capability baseline with exact compiler discovery parity and a byte-stable review report.**

## Accomplishments

- Added an Ajv 2020-12 schema with closed records and nonempty behavior, dimensions, ownership, and evidence.
- Discovered routes, mutations, preferences, themes, locales, permissions, scopes, and important states without regex-parsing TSX.
- Assigned every current atomic record to its redesign requirement and phase without deferred or merged placeholders.
- Added deterministic generation and stale-report enforcement for `docs/CAPABILITIES.md`.

## Task Commits

1. **Task 1: Implement strict schema, validation, discovery, and generation** - `214e399`
2. **Task 2: Populate every current atomic capability with ownership** - `c66386c`
3. **Canonical ordering hardening** - `afe264d`
4. **Task 3: Generate the human review report** - `c86ac79`

## Deviations from Plan

- Added an explicit canonical-order validation after initial population showed that deterministic rendering alone did not prove canonical JSON order.
- Permission discovery uses the seeded SQL catalog; all TS/TSX discovery uses the TypeScript compiler API.

## Issues Encountered

Dynamic endpoint expressions initially produced ambiguous source-anchor matches during one-time population. Rebuilding directly from stable discovered IDs preserved distinct HTTP methods and eliminated collisions.

## Next Phase Readiness

Browser fixtures can now trace critical-journey evidence to stable capability IDs, and CI can run one fail-closed inventory check.

---
*Completed: 2026-07-21*
