---
phase: 01-delivery-safeguards-and-behavioral-baseline
verified: 2026-07-21T19:50:23Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "DELV-02 Canonical version CI now compares pull requests against the immutable base SHA with full history and fails closed when CI cannot resolve a base."
  gaps_remaining: []
  regressions: []
---

# Phase 1: Delivery Safeguards and Behavioral Baseline Verification Report

**Phase Goal:** Maintainers and contributors can change the redesign with enforceable versioning, complete capability coverage, and regression evidence.
**Verified:** 2026-07-21T19:50:23Z
**Status:** passed
**Re-verification:** Yes — after gap closure commit `3c3dffc7b427213d0515b091a883c49d01c2a9bc`

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Maintainer can identify one canonical SemVer value that agrees across the application, build, image metadata, and release tag. | ✓ VERIFIED | `VERSION`, package, lockfile, backend metadata, Docker adapter, Compose argument, OCI label, and tag validation all consume `1.0.1`. Both version adapters printed `1.0.1`; backend metadata tests passed. |
| 2 | A protected-path change without a required bump is blocked with exact remediation, and the helper bumps only when required. | ✓ VERIFIED | The version job fetches full history and passes immutable `github.event.pull_request.base.sha` as `--base`. The named contract proves missing-base CI fails closed and an explicitly based protected unchanged-version diff fails with exact `node scripts/version.mjs bump` remediation. External PR run 29862886540 executed this path successfully against base `22f8a9c...`. |
| 3 | Contributor receives fast repository-configured pre-commit feedback while CI retains heavyweight backend and frontend gates. | ✓ VERIFIED | Regression check still reports `core.hooksPath=.githooks`; the two-line hook delegates only to `check --staged`. External PR run 29862886540 completed contracts, backend, frontend, and browser jobs successfully at the gap-fix head. |
| 4 | Maintainer can inspect an acceptance inventory covering every current route, action, permission, scope, preference, locale, theme, and important UI state. | ✓ VERIFIED | Strict discovery check reports 112 inventory records and 112 discovery candidates; generated report also has 112 records. Maintainer supplied explicit no-omissions approval. |
| 5 | CI blocks relevant backend, type, component, accessibility, visual, and critical-journey regressions. | ✓ VERIFIED | CI selects and aggregates backend, frontend, and pinned Playwright jobs. PR run 29862886540 passed all selected jobs and `delivery / gate`; ruleset 18341729 remains active and requires exact `delivery / gate` on `main` with no bypass actors. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `VERSION`, `scripts/lib/version-policy.mjs`, `scripts/version.mjs` | Canonical SemVer policy and CLI | ✓ VERIFIED | Substantive parser, protected-path classifier, mirror synchronization, check/bump/print adapters, and tests. |
| `backend/app/version.py`, `backend/app/api/meta.py` | Runtime version identity | ✓ VERIFIED | Root/image VERSION is validated and exposed by both metadata endpoints. |
| `Dockerfile`, `docker-compose.build.yml`, `scripts/docker-version.mjs` | Canonical image/build propagation | ✓ VERIFIED | Required build arg reaches OCI label and `/app/VERSION`; Compose and publisher use adapter output. |
| `.githooks/pre-commit`, `scripts/setup.mjs` | Fast configured local enforcement | ✓ VERIFIED | Hook is staged-only; setup is idempotent and this checkout is configured. |
| `capabilities/schema.json`, `capabilities/inventory.json`, `frontend/scripts/capabilities.mjs`, `docs/CAPABILITIES.md` | Strict complete acceptance inventory | ✓ VERIFIED | 112 source-anchored records, exact discovery parity, deterministic generated report. |
| Frontend component tests and helpers | Component and DOM-accessibility evidence | ✓ VERIFIED | Three suites, 11 tests, and axe assertions passed. |
| Playwright config, fixture, journey, and baselines | Critical journey, accessibility, visual evidence | ✓ VERIFIED | Four projects, stateful fail-closed fixture, four checkpoints, 16 PNGs; every live SHA-256 matches the approved manifest. The configured canonical path is `e2e/__screenshots__`, replacing the stale planned `*-snapshots` glob. |
| `.github/workflows/ci.yml`, `scripts/ci/aggregate.mjs` | Path-aware authoritative aggregate gate | ✓ VERIFIED | Canonical version checkout uses `fetch-depth: 0`; PR checks receive the immutable base SHA, non-PR checks receive the event-before SHA, and the aggregate gate remains wired. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `backend/app/api/meta.py` | `backend/app/version.py` → root `VERSION` | Package-relative import and validated file read | ✓ WIRED | Both public endpoints use the imported canonical value. |
| `.githooks/pre-commit` | `scripts/version.mjs` | `check --staged` | ✓ WIRED | No build, test, or network command is present in the hook. |
| `scripts/docker-version.mjs` | Compose/Docker/publisher | Validated VERSION environment/output | ✓ WIRED | Local Compose and Docker publication receive the same value. |
| `frontend/scripts/capabilities.mjs` | Inventory and report | Discovery, validation, deterministic generation | ✓ WIRED | Check proves source anchors, ownership, exact sets, ordering, and report byte freshness. |
| Browser journey | Stateful fixture | Same-origin intercepted API requests | ✓ WIRED | Exact watch payload mutates fixture state and refreshed dashboard assertions consume it. |
| CI selector | Heavy jobs → aggregate gate → ruleset | Job outputs, `needs` results, exact status context | ✓ WIRED | External ruleset is active and has no bypass actors. |
| Canonical version CI job | Protected PR diff | Git base comparison | ✓ WIRED | `.github/workflows/ci.yml` passes `github.event.pull_request.base.sha` to `check --base` after full-history checkout. Run 29862886540 logged base `22f8a9c...`, command `check --base "$BASE_SHA"`, and output `1.0.1`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| Metadata endpoints | `VERSION` | Root/image `VERSION` file | Yes, validated `1.0.1` | ✓ FLOWING |
| Capability report | Inventory records | Compiler/SQL discovery plus canonical JSON | Yes, 112/112 exact parity | ✓ FLOWING |
| Reference journey | Watch dates and mutation bodies | Exact intercepted API request | Yes, mutation changes refreshed dashboard data | ✓ FLOWING |
| Canonical version CI job | Changed protected paths | Immutable PR base SHA or push-before SHA | Yes; full-history Git diff, with CI missing-base fail-closed behavior | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command/evidence | Result | Status |
|---|---|---|---|
| Explicit delivery contracts | `npm --prefix frontend run test:contracts` | 45/45 passed, including the named missing-base/protected-diff test and version-job-specific workflow assertions | ✓ PASS |
| Capability completeness/freshness | `node frontend/scripts/capabilities.mjs check` | 112 records, 112 candidates | ✓ PASS |
| Runtime metadata | `python -m pytest backend/tests/test_meta.py -q` | 6 passed | ✓ PASS |
| Component/accessibility baseline | Focused Vitest command for App, Settings, TitleDetail | 3 files, 11 tests passed | ✓ PASS |
| Approved visual artifacts | SHA-256 comparison against approved manifest | 16 found, 0 missing/mismatched | ✓ PASS |
| Actual external baseline generation | GitHub Actions run 29850978099 | Success; artifact 8503379016 from commit `21d1529c...` | ✓ PASS |
| Ordinary immutable comparison | GitHub Actions run 29862886540 at `3c3dffc7...` | Success; Canonical version used full history and immutable base `22f8a9c...` | ✓ PASS |
| Missing-base CI and protected unchanged-version diff | Named Node contract in `scripts/tests/version-policy.test.mjs` | Missing base exits non-zero; explicit protected diff exits non-zero; both print exact remediation | ✓ PASS |
| Required aggregate after gap fix | GitHub Actions run 29862886540 | All selected children and `delivery / gate` completed successfully | ✓ PASS |

### Probe Execution

No phase-specific `probe-*.sh` scripts were declared. The explicit Node contract suite was run directly.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| DELV-01 | 01-01, 01-03, 01-04, 01-09, 01-10 | One canonical version across runtime/build/image/tag policy | ✓ SATISFIED | All records and adapters agree at `1.0.1`; Docker and tag contracts are wired. |
| DELV-02 | 01-01, 01-03, 01-09, 01-10 | Blocking CI error and exact remediation for protected changes | ✓ SATISFIED | Authoritative PR CI passes the immutable base SHA after full-history checkout; the behavioral contract proves missing-base CI and unchanged protected diffs fail closed with exact remediation. |
| DELV-03 | 01-01, 01-03, 01-10 | Idempotent bounded bump helper | ✓ SATISFIED | Named behavior test proves first bump and byte-preserving second run; writes are limited to three records. |
| DELV-04 | 01-01, 01-04, 01-09, 01-10 | Fast configured pre-commit; heavy checks in CI | ✓ SATISFIED | Hook configuration and staged-only behavior verified; heavy jobs remain in CI. |
| DELV-05 | 01-01, 01-02, 01-05, 01-07, 01-10 | Complete acceptance inventory | ✓ SATISFIED | Strict 112/112 machine parity plus supplied maintainer no-omissions approval. |
| DELV-06 | 01-01, 01-02, 01-05, 01-06, 01-08, 01-09, 01-10 | Backend, type, component, accessibility, visual, and journey CI | ✓ SATISFIED | Local focused suites and external all-surface PR comparison passed; exact gate is required externally. |

No Phase 1 requirements were orphaned from plans.

### Prohibition Verification

| Prohibition | Status | Evidence |
|---|---|---|
| Bump must not create commits/tags or modify files outside the three version records. | ✓ VERIFIED | CLI contains no commit/tag operation; named temp-repository test proves byte-preserving second run and bounded writes. |
| Capability inventory must not omit, defer, or merge current capabilities. | ✓ VERIFIED | Exact 112/112 discovery parity and supplied maintainer review confirming no omissions. |
| Visual baselines must not be auto-accepted or unexplained skips treated as success. | ✓ VERIFIED | Update flag exists only on dispatch generation; ordinary CI compares. Aggregate script accepts skips only when selector outputs explicitly mark jobs unselected. Maintainer approved all 16 manifest-backed images. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| — | — | None in gap-fix files | ℹ️ Info | The CLI `console.log` calls are intentional command output, not console-only implementations. `git diff --check` passed, and the fix commit changes only the four declared files. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in Phase 1 implementation files. Scanner hits were future-roadmap placeholders, dependency package names, or ordinary form placeholder attributes.

### Human Verification Required

None outstanding. The supplied maintainer evidence resolves visual-intent and capability-omission review, and the live REST ruleset response resolves repository-external enforcement configuration.

### Gaps Summary

The sole previous blocker is closed. Canonical version CI now has full history, compares PRs to the immutable event base SHA, and fails closed rather than silently comparing HEAD to itself. The 45-test contract suite and external PR run 29862886540 verify the corrected path. Quick regression checks found no regression to the other four truths, and previously accepted human/external evidence remains preserved.

---

_Verified: 2026-07-21T19:50:23Z_
_Verifier: the agent (gsd-verifier)_
