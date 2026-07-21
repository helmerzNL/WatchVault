# Phase 1: Delivery Safeguards and Behavioral Baseline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-07-21
**Phase:** 1-delivery-safeguards-and-behavioral-baseline
**Areas discussed:** Canonical version source and synchronization, protected-path policy and remediation, capability-inventory structure and ownership, regression gates and local-check boundaries

---

## Canonical version source and synchronization

### Source of truth

| Option | Description | Selected |
|--------|-------------|----------|
| Root `VERSION` file | Stack-neutral source for scripts, Docker, app metadata, and tags | Yes |
| `frontend/package.json` | Reuse the existing field but make the frontend authoritative | |
| Git tag only | Derive version in CI without a committed source | |

**User's choice:** Root `VERSION` file.

### Propagation

| Option | Description | Selected |
|--------|-------------|----------|
| Generated mirrors and verification | Synchronize package manifests, OCI labels, backend metadata, and release tags | Yes |
| Build-time only | Read the version during builds while leaving package metadata unrelated | |
| Minimal | Limit use to CI, tags, and image labels | |

**User's choice:** Generated mirrors and verification.

### Helper behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect with default patch | Compare with merge base, bump once when needed, allow minor/major overrides | Yes |
| Always require bump type | Require an explicit release level for every invocation | |
| Patch only | Reserve minor and major releases for a separate process | |

**User's choice:** Auto-detect with default patch.

### Phase 1 version

| Option | Description | Selected |
|--------|-------------|----------|
| `1.0.1` | Treat existing `1.0.0` as baseline and patch-bump Phase 1 delivery changes | Yes |
| `1.1.0` | Treat the delivery foundation as a minor release | |
| Keep `1.0.0` | Add safeguards without incrementing the version | |

**User's choice:** `1.0.1`.

---

## Protected-path policy and remediation

### Protected scope

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit comprehensive set | Protect backend, frontend, plugins, Home Assistant, deploy, scripts, Docker, compose, and workflows | Yes |
| Core runtime only | Exclude integrations and workflows | |
| Broad inverse allowlist | Protect almost everything except known documentation/data paths | |

**User's choice:** Explicit comprehensive set.

### Policy ownership

| Option | Description | Selected |
|--------|-------------|----------|
| One machine-readable root policy | CI, helper, and hook consume identical include/exclude rules | Yes |
| Helper owns policy | CI and hook invoke the helper as the only policy engine | |
| Duplicate native patterns | Maintain separate path lists in workflow and hook | |

**User's choice:** One machine-readable root policy.

### Remediation command

| Option | Description | Selected |
|--------|-------------|----------|
| `node scripts/version.mjs bump` | Cross-platform command with patch default and minor/major overrides | Yes |
| npm frontend script | Route delivery tooling through the frontend package | |
| Platform scripts | Maintain separate shell and PowerShell commands | |

**User's choice:** `node scripts/version.mjs bump`.

### Pre-commit behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Blocking version and mirror checks | Check staged protected changes and synchronized metadata without heavy tests | Yes |
| Warning only | Leave all blocking behavior to CI | |
| Run tests too | Add frontend and backend checks to every commit | |

**User's choice:** Blocking version and mirror checks only.

---

## Capability-inventory structure and ownership

### Canonical artifact

| Option | Description | Selected |
|--------|-------------|----------|
| JSON plus generated Markdown | Machine validation with a readable review artifact | Yes |
| Markdown only | Human-readable tables without robust structural validation | |
| Tests only | Treat regression cases as the inventory | |

**User's choice:** JSON plus generated Markdown.

### Entry granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic capability IDs | One stable entry per route, action, rule, behavior, obligation, or state | Yes |
| One row per screen | Summarize all screen behavior in a broad row | |
| One row per requirement | Map only at roadmap-requirement granularity | |

**User's choice:** Atomic capability IDs.

### Required evidence

| Option | Description | Selected |
|--------|-------------|----------|
| Complete ownership map | Source, behavior, dimensions, roadmap owner, and regression evidence | Yes |
| Source catalog only | Record current code and assign redesign ownership later | |
| Critical journey only | Fully map only dashboard/search/title/history | |

**User's choice:** Complete ownership map.

### CI trust model

| Option | Description | Selected |
|--------|-------------|----------|
| Strict validator | Block schema, reference, report freshness, and discoverable catalog gaps | Yes |
| Schema validation only | Validate shape without comparing code surfaces | |
| Advisory report | Report drift without blocking | |

**User's choice:** Strict validator.

---

## Regression gates and local-check boundaries

### Frontend stack

| Option | Description | Selected |
|--------|-------------|----------|
| Vitest, Testing Library, axe, and Playwright | Fast component/a11y checks plus real-browser journeys and screenshots | Yes |
| Playwright only | Put every frontend regression in browser tests | |
| Vitest only | Defer real-browser and visual coverage | |

**User's choice:** Vitest, Testing Library, axe, and Playwright.

### Browser data boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic browser-level API fixtures | Exercise real React routing while pytest separately covers backend behavior | Yes |
| Full Docker Compose stack | Run browsers against seeded PostgreSQL and all services | |
| Hybrid | Mocked PR tests plus a nightly full-stack journey | |

**User's choice:** Deterministic browser-level API fixtures.

### Blocking browser matrix

| Option | Description | Selected |
|--------|-------------|----------|
| Pinned Chromium, desktop/mobile, dark/light | Cover both target form factors and themes across the reference journey | Yes |
| Chromium desktop/dark only | Start with one narrow baseline | |
| Three-browser matrix | Run Chromium, Firefox, and WebKit across all dimensions | |

**User's choice:** Pinned Chromium at desktop/mobile sizes in dark/light modes.

### CI selection

| Option | Description | Selected |
|--------|-------------|----------|
| Path-aware PR matrix plus full main/tag suite | Always validate version/inventory, select relevant heavy jobs on PRs, run all on main/tags | Yes |
| Every check on every PR | Ignore changed surfaces | |
| Browser checks nightly only | Keep visual and journey gates off pull requests | |

**User's choice:** Path-aware PR matrix plus full main/tag suite.

---

## the agent's Discretion

- Exact policy/inventory filenames and schemas.
- Hook bootstrap details.
- Snapshot thresholds, artifact retention, and fixture layout.

## Deferred Ideas

None.
