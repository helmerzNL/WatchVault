---
phase: 01-delivery-safeguards-and-behavioral-baseline
plan: "10"
subsystem: delivery-authority
tags: [visual-baselines, human-approval, rulesets, required-checks]
requires:
  - phase: 01-delivery-safeguards-and-behavioral-baseline
    provides: Pinned baseline generation and stable aggregate CI gate
provides:
  - Human-approved 16-image Linux Chromium behavioral baseline
  - Immutable ordinary CI comparison against the approved baseline
  - Live main-branch pull-request rule requiring exact delivery / gate without bypass
affects: [02-typed-data-and-pwa-state-safety, 03-cinematic-design-system, 05-reference-journey]
tech-stack:
  added: []
  patterns: [manifest-backed visual approval, repository-external required status]
key-files:
  created: [frontend/e2e/__screenshots__/reference-journey.spec.ts/**]
  modified: [.github/workflows/ci.yml, frontend/scripts/workflow-contract.test.mjs]
key-decisions:
  - "Only the pinned Linux dispatch may create baseline candidates; ordinary CI compares without update flags."
  - "Human approval covers visual intent, while manifest hashes and CI cover provenance and reproducibility."
  - "The live ruleset targets main, requires pull requests and exact delivery / gate, and has no bypass actors."
requirements-completed: [DELV-01, DELV-02, DELV-03, DELV-04, DELV-05, DELV-06]
coverage:
  - id: D1
    description: "All 16 baseline images were explicitly reviewed and approved by the maintainer."
    requirement: DELV-06
    verification:
      - kind: human
        ref: "Maintainer approval on 2026-07-21"
        status: pass
    human_judgment: true
  - id: D2
    description: "The live main ruleset requires pull requests and exact delivery / gate with an empty bypass list."
    requirement: DELV-06
    verification:
      - kind: external
        ref: "GitHub ruleset 18341729"
        status: pass
    human_judgment: false
  - id: D3
    description: "The 112-record capability report was reviewed without omissions or merged behaviors."
    requirement: DELV-05
    verification:
      - kind: human
        ref: "Maintainer capability review on 2026-07-21"
        status: pass
    human_judgment: true
duration: 45min
completed: 2026-07-21
status: complete
---

# Phase 1 Plan 10: Baseline Approval and Required Gate Summary

**The current WatchVault behavior is now frozen in 16 approved Linux/Chromium images, compared immutably by CI, and protected on `main` by the exact required `delivery / gate` status without bypass.**

## Accomplishments

- Generated the authoritative candidates in pinned container `mcr.microsoft.com/playwright:v1.61.1-noble` with Playwright `1.61.1`.
- Verified artifact run `29850978099`, artifact `8503379016`, and source commit `21d1529c69787875f21d86ad333a68649d667ea9`.
- Independently matched all manifest byte sizes and SHA-256 values before copying the 16 candidates into the canonical snapshot tree.
- Received explicit human approval for every image and confirmation that the 112-record capability report omits no current behavior.
- Proved ordinary immutable comparison in successful pull-request run `29851346956`.
- Verified live active ruleset `18341729` targets only `refs/heads/main`, requires pull requests and exact status `delivery / gate`, and contains no bypass actors.
- Proved a second patch bump was byte-preserving at canonical version `1.0.1`.
- Closed the independent verifier's CI-base gap and passed re-verification with all five phase truths and all six DELV requirements satisfied.

## Approved Manifest

| Project | Checkpoint | SHA-256 |
|---------|------------|---------|
| desktop-dark | dashboard | `faf58ebbf125c45413b69b48b4c853c6c0698344000cb2f8877f1c67ac5dcce7` |
| desktop-dark | search | `4a707de29dcfece66ac8a5d3b4fc2978056d279b4f66cd11d394393b465d97f5` |
| desktop-dark | title | `f8915c2dfbb5c04d9fbe510b29ecb3dfa76f4e74a3b42b65da66c9ebd6adc58a` |
| desktop-dark | dashboard-after-watch | `134418b7ecb7457a02f497b9bab6b1c5b8e0347deaa8bcd5ac0288977b092dcf` |
| desktop-light | dashboard | `86e5392d997fba654e21a0f90e8d6895c81bec978cad1c41e6ea9ad1a8e8ee69` |
| desktop-light | search | `59fa8b848ff7e0aff0999e897e25a2ce73b0d7fa9d7255d4551aa39ccd79cd06` |
| desktop-light | title | `d046b46359ff8fe874f22a500a747f41783f7eeb6a5db2c3a68894eb670b222b` |
| desktop-light | dashboard-after-watch | `185a4b8c4b1f698dd275c6f3ec3db0c4eaaa380104813d99b762abc6494e6f39` |
| mobile-dark | dashboard | `c5d54223123636d8b0b811facfb7f07853b34741da5e3619a7b3b18704f48078` |
| mobile-dark | search | `0017e9747a52b350e375e2d815e780da802061ff9b2a4e4ead09d9aeade4436d` |
| mobile-dark | title | `885057678a16844bd3c4696db841d8390966ce29263359014bf7265e5acb70c2` |
| mobile-dark | dashboard-after-watch | `451935548e4f825239fc6ae5aa0dbf8b8c7594661b7ad4939646705eecf4294f` |
| mobile-light | dashboard | `2493cf7851264dfb5be3eea27a4cc3be80b25425c678237ecc4938b636e019bd` |
| mobile-light | search | `799787127a95bc6b31623afc729a2982b9e51593bbe1f469a52b6e20f699aecb` |
| mobile-light | title | `cc6b2d92faa1ae5567bec4dcddd3611ef8432416ceb2804141876b270f6276b7` |
| mobile-light | dashboard-after-watch | `836b93fb74551d36a45c365d3ea1b3a5714817e0846d90f18277e34010a868a3` |

## Task Commits

1. **Task 1: Add provenance-complete baseline generation** - `9322dec`, `21d1529`
2. **Task 1: Commit reviewed baseline candidates and immutable comparison** - `d9e363a`
3. **Task 2: Configure required aggregate gate** - external ruleset `18341729`
4. **Gap closure: Enforce immutable PR base in canonical version CI** - `3c3dffc`

## Deviations from Plan

- The first dispatch exposed that the artifact glob still referenced Playwright's obsolete `*-snapshots` layout. The workflow and contract now use the configured `e2e/__screenshots__` tree.
- The second candidate exposed that provenance existed only in the artifact name. A deterministic JSON manifest now records source commit, exact Playwright version, container identity, count, byte size, and SHA-256 for every image.
- The workflow could be dispatched from the published feature branch before merge, allowing the complete human checkpoint to finish without weakening default-branch controls.
- Independent verification found that the Canonical version job's shallow checkout could collapse its diff to HEAD. The job now fetches full history, receives the immutable PR base SHA explicitly, and the CLI fails closed when CI cannot resolve a comparison base.

## Issues Encountered

GitHub's GraphQL API rate limit blocked one convenience check query. REST ruleset and Actions endpoints remained available and supplied the authoritative verification evidence.

## Next Phase Readiness

Delivery safeguards are complete and externally enforceable. Phase 2 can now harden authenticated and scoped PWA data without losing current behavior or bypassing version, capability, browser, and publication gates.

---
*Completed: 2026-07-21*
