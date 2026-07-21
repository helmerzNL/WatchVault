---
phase: 1
slug: delivery-safeguards-and-behavioral-baseline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-21
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0; Node `node:test`; Vitest 4.1.10 with jsdom, Testing Library, and axe-core; Playwright Test 1.61.1 with Chromium |
| **Config file** | Backend: none; frontend and browser configs are installed in Wave 0 |
| **Quick run command** | `node --test scripts/tests/*.test.mjs frontend/scripts/*.test.mjs && python -m pytest backend/tests -q && npm --prefix frontend run test -- --run` |
| **Full suite command** | `node scripts/version.mjs check && node frontend/scripts/capabilities.mjs check && python -m pytest backend/tests && npm --prefix frontend run build && npm --prefix frontend run test -- --run && npm --prefix frontend run test:e2e` |
| **Estimated runtime** | Quick: <120 seconds; full: <10 minutes in CI |

---

## Sampling Rate

- **After every task commit:** Run the focused test file and `node scripts/version.mjs check --staged` when protected files are staged.
- **After every plan wave:** Run version and inventory checks, all pytest tests, the frontend build, and all Vitest tests.
- **Before `/gsd-verify-work`:** Run the complete suite, including all four Playwright projects.
- **Max feedback latency:** 120 seconds for task-level checks; 10 minutes for the complete CI gate.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-TBD-01 | TBD | 0 | DELV-01 | T-01 / T-02 | Version parsing and Git path handling reject malformed or unsafe input | unit + integration | `node --test scripts/tests/version-policy.test.mjs && python -m pytest backend/tests/test_meta.py -q && node scripts/version.mjs check` | ❌ W0 | ⬜ pending |
| 01-TBD-02 | TBD | 0 | DELV-02 | T-01 / T-06 | Protected changes cannot pass without a sufficient bump and exact remediation | temp-Git integration | `node --test scripts/tests/version-policy.test.mjs` | ❌ W0 | ⬜ pending |
| 01-TBD-03 | TBD | 0 | DELV-03 | T-01 | Patch/minor/major bumps are correct, bounded, and idempotent | unit + temp workspace | `node --test scripts/tests/version-policy.test.mjs` | ❌ W0 | ⬜ pending |
| 01-TBD-04 | TBD | 0 | DELV-04 | T-06 | Hook checks staged state only; CI remains authoritative when hooks are bypassed | temp-Git commit integration | `node --test scripts/tests/version-policy.test.mjs` | ❌ W0 | ⬜ pending |
| 01-TBD-05 | TBD | 0 | DELV-05 | T-02 / T-05 | Strict schema, safe source references, stable IDs, and complete discoverable catalogs | validator + snapshot | `node --test frontend/scripts/capabilities.test.mjs && node frontend/scripts/capabilities.mjs check` | ❌ W0 | ⬜ pending |
| 01-TBD-06 | TBD | 0 | DELV-06 | T-03 / T-04 / T-06 | Synthetic fixtures contain no credentials; PR jobs have read-only permissions and an aggregate gate | backend + component + a11y + E2E | Full suite command above | pytest ✅; frontend/browser ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `scripts/tests/version-policy.test.mjs` — DELV-01 through DELV-04 version, path, tag, and hook coverage.
- [ ] `backend/tests/test_meta.py` — canonical runtime version exposure.
- [ ] `frontend/scripts/capabilities.test.mjs` — DELV-05 schema, discovery, reference, and generated-report coverage.
- [ ] `frontend/vitest.config.ts` and `frontend/src/test/setup.ts` — component and axe test infrastructure.
- [ ] Representative `*.test.tsx` files — auth gates, theme/preferences, semantic states, and one mutation.
- [ ] `frontend/playwright.config.ts`, deterministic fixtures, critical journey, axe checks, and 16 reviewed snapshots.
- [ ] Frontend test dependencies and pinned Chromium provisioning.
- [ ] `.github/workflows/ci.yml` — path-aware jobs and stable aggregate `delivery / gate`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GitHub ruleset requires `delivery / gate` before merge | DELV-06 | Repository rulesets are external to committed source | Inspect the default-branch ruleset after CI lands and confirm `delivery / gate` is a required status check; attempt or inspect a PR with a failing child job and confirm merge is blocked |
| Initial desktop/mobile dark/light screenshots are intentional | DELV-06 | Baseline appearance requires human approval before future pixel diffs can be authoritative | Review all 16 Playwright snapshots and approve them before marking Wave 0 complete |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Task-level feedback latency is under 120 seconds.
- [ ] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
