import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  REMEDIATION,
  bumpVersion,
  classifyProtectedPath,
  compareVersions,
  formatVersion,
  isSufficientVersion,
  normalizeGitPath,
  parseStableVersion,
  protectedChangesRequireBump,
  readVersionRecords,
  writeVersionRecords,
} from "../lib/version-policy.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const VERSION_CLI = join(ROOT, "scripts", "version.mjs");
const SETUP_CLI = join(ROOT, "scripts", "setup.mjs");
const HOOK = join(ROOT, ".githooks", "pre-commit");

const POLICY = {
  include: [
    "backend/**",
    "frontend/**",
    "plugins/**",
    "homeassistant/**",
    "deploy/**",
    "scripts/**",
    "Dockerfile",
    "docker-compose*.yml",
    ".github/workflows/**",
  ],
  exclude: [
    "backend/**/*.md",
    "frontend/**/*.md",
    "scripts/tests/**",
  ],
};

function git(cwd, ...args) {
  return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

function writeManifest(root, version) {
  const frontend = join(root, "frontend");
  mkdirSync(frontend, { recursive: true });
  writeFileSync(
    join(frontend, "package.json"),
    `${JSON.stringify({ name: "fixture", version }, null, 2)}\n`,
  );
  writeFileSync(
    join(frontend, "package-lock.json"),
    `${JSON.stringify({
      name: "fixture",
      version,
      lockfileVersion: 3,
      packages: { "": { name: "fixture", version } },
    }, null, 2)}\n`,
  );
}

function createRepository() {
  const root = mkdtempSync(join(tmpdir(), "watchvault-version-"));
  git(root, "init", "-q");
  git(root, "config", "user.email", "watchvault-tests@example.invalid");
  git(root, "config", "user.name", "WatchVault Tests");
  writeFileSync(join(root, "VERSION"), "1.0.0\n");
  writeManifest(root, "1.0.0");
  writeFileSync(join(root, "version-policy.json"), `${JSON.stringify(POLICY, null, 2)}\n`);
  mkdirSync(join(root, "backend"), { recursive: true });
  writeFileSync(join(root, "backend", "app.py"), "baseline\n");
  git(root, "add", ".");
  git(root, "commit", "-qm", "baseline");
  return root;
}

test("parse stable SemVer and reject empty, malformed, or prerelease values", () => {
  assert.deepEqual(parseStableVersion("1.0.1\n"), { major: 1, minor: 0, patch: 1 });
  for (const invalid of ["", "1", "1.0", "v1.0.1", "1.0.1-beta.1", "01.0.1"]) {
    assert.throws(() => parseStableVersion(invalid), /stable SemVer/i);
  }
});

test("format, compare, and bump patch minor major versions exactly", () => {
  assert.equal(formatVersion({ major: 1, minor: 2, patch: 3 }), "1.2.3");
  assert.equal(compareVersions("1.0.1", "1.0.0"), 1);
  assert.equal(compareVersions("1.0.1", "1.0.1"), 0);
  assert.equal(compareVersions("1.0.0", "1.0.1"), -1);
  assert.equal(bumpVersion("1.2.3"), "1.2.4");
  assert.equal(bumpVersion("1.2.3", "minor"), "1.3.0");
  assert.equal(bumpVersion("1.2.3", "major"), "2.0.0");
});

test("normalize Git separators and reject absolute or traversal paths", () => {
  assert.equal(normalizeGitPath("frontend\\src\\App.tsx"), "frontend/src/App.tsx");
  assert.equal(normalizeGitPath("./backend/app.py"), "backend/app.py");
  for (const invalid of ["../backend/app.py", "frontend/../../secret", "/etc/passwd", "C:\\secret"]) {
    assert.throws(() => normalizeGitPath(invalid), /relative|traversal|absolute/i);
  }
});

test("classify exact prefix and exclusion rules from one policy", () => {
  assert.equal(classifyProtectedPath("Dockerfile", POLICY), true);
  assert.equal(classifyProtectedPath("frontend/src/App.tsx", POLICY), true);
  assert.equal(classifyProtectedPath(".github/workflows/ci.yml", POLICY), true);
  assert.equal(classifyProtectedPath("frontend/README.md", POLICY), false);
  assert.equal(classifyProtectedPath("scripts/tests/version-policy.test.mjs", POLICY), false);
  assert.equal(classifyProtectedPath("docs/guide.md", POLICY), false);
});

test("protected aggregate changes require a bump while empty and unprotected changes do not", () => {
  assert.equal(protectedChangesRequireBump([], POLICY), false);
  assert.equal(protectedChangesRequireBump(["docs/guide.md"], POLICY), false);
  assert.equal(
    protectedChangesRequireBump(["docs/guide.md", "backend/app/api/meta.py"], POLICY),
    true,
  );
});

test("equal versions fail only when a protected bump is required", () => {
  assert.equal(isSufficientVersion("1.0.0", "1.0.0", [], POLICY), true);
  assert.equal(
    isSufficientVersion("1.0.0", "1.0.0", ["frontend/src/App.tsx"], POLICY),
    false,
  );
  assert.equal(
    isSufficientVersion("1.0.0", "1.0.1", ["frontend/src/App.tsx"], POLICY),
    true,
  );
  assert.equal(
    isSufficientVersion("1.0.1", "1.0.0", ["frontend/src/App.tsx"], POLICY),
    false,
  );
});

test("read and synchronize VERSION package and lockfile root records", () => {
  const root = mkdtempSync(join(tmpdir(), "watchvault-records-"));
  writeFileSync(join(root, "VERSION"), "1.0.0\n");
  writeManifest(root, "1.0.0");
  assert.deepEqual(readVersionRecords(root), {
    canonical: "1.0.0",
    package: "1.0.0",
    lockfile: "1.0.0",
  });
  writeVersionRecords(root, "1.0.1");
  assert.deepEqual(readVersionRecords(root), {
    canonical: "1.0.1",
    package: "1.0.1",
    lockfile: "1.0.1",
  });
});

test("CLI bump reaches 1.0.1 and second run is a no-op", { skip: !existsSync(VERSION_CLI) }, () => {
  const root = createRepository();
  writeFileSync(join(root, "backend", "app.py"), "protected change\n");
  const first = spawnSync(process.execPath, [VERSION_CLI, "bump", "--base", "HEAD"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(first.status, 0, first.stderr);
  assert.deepEqual(readVersionRecords(root), {
    canonical: "1.0.1",
    package: "1.0.1",
    lockfile: "1.0.1",
  });
  const before = [
    readFileSync(join(root, "VERSION"), "utf8"),
    readFileSync(join(root, "frontend", "package.json"), "utf8"),
    readFileSync(join(root, "frontend", "package-lock.json"), "utf8"),
  ];
  const second = spawnSync(process.execPath, [VERSION_CLI, "bump", "--base", "HEAD"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(second.status, 0, second.stderr);
  assert.deepEqual([
    readFileSync(join(root, "VERSION"), "utf8"),
    readFileSync(join(root, "frontend", "package.json"), "utf8"),
    readFileSync(join(root, "frontend", "package-lock.json"), "utf8"),
  ], before);
});

test("staged check ignores an unstaged bump and prints exact remediation", {
  skip: !existsSync(VERSION_CLI),
}, () => {
  const root = createRepository();
  writeFileSync(join(root, "backend", "app.py"), "staged protected change\n");
  git(root, "add", "backend/app.py");
  writeFileSync(join(root, "VERSION"), "1.0.1\n");
  const result = spawnSync(process.execPath, [VERSION_CLI, "check", "--staged"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, new RegExp(`${REMEDIATION}$`, "m"));
});

test("CI fails closed without a resolvable base and explicit base catches protected changes", {
  skip: !existsSync(VERSION_CLI),
}, () => {
  const root = createRepository();
  writeFileSync(join(root, "backend", "app.py"), "protected CI change\n");
  const ciEnvironment = {
    ...process.env,
    CI: "true",
    GITHUB_BASE_REF: "",
    GITHUB_EVENT_BEFORE: "",
  };
  const missingBase = spawnSync(process.execPath, [VERSION_CLI, "check"], {
    cwd: root,
    encoding: "utf8",
    env: ciEnvironment,
  });
  assert.notEqual(missingBase.status, 0);
  assert.match(`${missingBase.stdout}${missingBase.stderr}`, /Unable to resolve comparison base in CI/);
  assert.match(`${missingBase.stdout}${missingBase.stderr}`, new RegExp(`${REMEDIATION}$`, "m"));

  const explicitBase = spawnSync(
    process.execPath,
    [VERSION_CLI, "check", "--base", git(root, "rev-parse", "HEAD").trim()],
    { cwd: root, encoding: "utf8", env: ciEnvironment },
  );
  assert.notEqual(explicitBase.status, 0);
  assert.match(`${explicitBase.stdout}${explicitBase.stderr}`, /Protected changes require a version/);
  assert.match(`${explicitBase.stdout}${explicitBase.stderr}`, new RegExp(`${REMEDIATION}$`, "m"));
});

test("setup configures the committed staged-only hook idempotently", {
  skip: !existsSync(SETUP_CLI) || !existsSync(HOOK),
}, () => {
  const root = createRepository();
  execFileSync(process.execPath, [SETUP_CLI], { cwd: root });
  execFileSync(process.execPath, [SETUP_CLI], { cwd: root });
  assert.equal(git(root, "config", "--local", "--get", "core.hooksPath").trim(), ".githooks");
  assert.match(
    readFileSync(HOOK, "utf8").replaceAll("\r\n", "\n"),
    /^#!\/bin\/sh\nexec node scripts\/version\.mjs check --staged\n$/,
  );
});
