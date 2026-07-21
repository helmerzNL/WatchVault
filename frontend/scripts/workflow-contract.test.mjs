import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const ciPath = join(ROOT, ".github", "workflows", "ci.yml");

if (!existsSync(ciPath)) {
  throw new Error(".github/workflows/ci.yml");
}

const { parse } = await import("yaml");
const ciSource = readFileSync(ciPath, "utf8");
const dockerSource = readFileSync(join(ROOT, ".github", "workflows", "docker.yml"), "utf8");
const ci = parse(ciSource);
const docker = parse(dockerSource);

test("both workflows parse as YAML mappings", () => {
  assert.equal(typeof ci, "object");
  assert.equal(typeof docker, "object");
});

test("CI uses safe triggers, read-only defaults, and full history", () => {
  assert.match(ciSource, /^\s*pull_request:\s*$/m);
  assert.doesNotMatch(ciSource, /pull_request_target/);
  assert.match(ciSource, /branches:\s*\[\s*main\s*\]/);
  assert.match(ciSource, /tags:\s*\[\s*["']?v\*["']?\s*\]/);
  assert.match(ciSource, /^permissions:\s*\n\s+contents:\s+read/m);
  assert.match(ciSource, /fetch-depth:\s*0/);
});

test("clean runners provision Python Node npm and the pinned Playwright environment", () => {
  assert.match(ciSource, /python-version:\s*["']?3\.12["']?/);
  assert.match(ciSource, /backend\/requirements\.txt/);
  assert.match(ciSource, /backend\/requirements-dev\.txt/);
  assert.match(ciSource, /node-version:\s*["']?20\.19/);
  assert.match(ciSource, /npm ci --prefix frontend/);
  const image = "mcr.microsoft.com/playwright:v1.61.1-noble";
  assert.ok(ciSource.split(image).length >= 3, "comparison and generation must share the pinned image");
  assert.match(ciSource, /playwright install chromium/);
});

test("CI runs every explicit repository contract suite", () => {
  assert.match(ciSource, /npm --prefix frontend run test:contracts/);
  const packageJson = JSON.parse(readFileSync(join(ROOT, "frontend", "package.json"), "utf8"));
  const command = packageJson.scripts?.["test:contracts"] ?? "";
  for (const contract of [
    "version-policy.test.mjs",
    "docker-contract.test.mjs",
    "ci-changes.test.mjs",
    "workflow-contract.test.mjs",
    "capabilities.test.mjs",
  ]) {
    assert.match(command, new RegExp(contract.replaceAll(".", "\\.")));
  }
  assert.doesNotMatch(command, /\*\.test\.mjs/);
});

test("selection, E2E, baseline generation, and aggregate gate are explicit", () => {
  assert.match(ciSource, /scripts\/ci-changes\.mjs/);
  assert.match(ciSource, /playwright test/);
  assert.match(ciSource, /workflow_dispatch/);
  assert.match(ciSource, /16/);
  assert.match(ciSource, /e2e\/__screenshots__/);
  assert.match(ciSource, /SOURCE_COMMIT:\s*\$\{\{\s*github\.sha\s*\}\}/);
  assert.match(ciSource, /baseline-manifest\.mjs/);
  assert.match(ciSource, /sha256|SHA-256/i);
  assert.match(ciSource, /name:\s*delivery \/ gate/);
  assert.match(ciSource, /if:\s*\$\{\{\s*always\(\)\s*\}\}/);
  assert.ok(
    ci.jobs.browser.steps.some((step) => step.run === "npx playwright test"),
    "ordinary browser CI must compare without updating snapshots",
  );
  assert.ok(
    ci.jobs.baselines.steps.some((step) => step.run === "npx playwright test --update-snapshots"),
    "dispatch generation must be the only snapshot update path",
  );
});

test("publication is gated and receives adapter-derived VERSION", () => {
  assert.match(ciSource, /uses:\s*\.\/\.github\/workflows\/docker\.yml/);
  assert.match(ciSource, /needs:.*gate/);
  assert.match(dockerSource, /workflow_call/);
  assert.match(dockerSource, /node scripts\/docker-version\.mjs print/);
  assert.match(dockerSource, /build-args:\s*\|[\s\S]*VERSION=/);
  assert.match(dockerSource, /org\.opencontainers\.image\.version/);
});
