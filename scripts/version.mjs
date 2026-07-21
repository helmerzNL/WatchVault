#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

import {
  REMEDIATION,
  bumpVersion,
  compareVersions,
  isSufficientVersion,
  parseStableVersion,
  readVersionPolicy,
  readVersionRecords,
  writeVersionRecords,
} from "./lib/version-policy.mjs";

const ROOT = process.cwd();

function git(args, options = {}) {
  return execFileSync("git", args, {
    cwd: ROOT,
    encoding: options.encoding ?? "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function validateRef(ref) {
  if (!ref || ref.startsWith("-") || !/^[A-Za-z0-9_./@{}^~:+-]+$/.test(ref)) {
    throw new Error(`Unsafe Git ref: ${JSON.stringify(ref)}`);
  }
  return ref;
}

function refExists(ref) {
  try {
    git(["rev-parse", "--verify", "--quiet", `${validateRef(ref)}^{commit}`]);
    return true;
  } catch {
    return false;
  }
}

function optionValue(args, name) {
  const index = args.indexOf(name);
  if (index === -1) return undefined;
  if (!args[index + 1]) throw new Error(`${name} requires a value`);
  return args[index + 1];
}

function resolveBase(args) {
  const explicit = optionValue(args, "--base");
  if (explicit) return validateRef(explicit);

  const candidates = [];
  if (process.env.GITHUB_BASE_REF) candidates.push(`origin/${process.env.GITHUB_BASE_REF}`);
  if (process.env.GITHUB_EVENT_BEFORE && !/^0+$/.test(process.env.GITHUB_EVENT_BEFORE)) {
    candidates.push(process.env.GITHUB_EVENT_BEFORE);
  }
  candidates.push("origin/main");
  const resolved = candidates.find(refExists);
  if (resolved) return resolved;
  if (process.env.CI || process.env.GITHUB_ACTIONS === "true") {
    throw new Error("Unable to resolve comparison base in CI; pass --base <commit-sha>");
  }
  return "HEAD";
}

function readJsonAtRef(ref, path) {
  try {
    return JSON.parse(git(["show", `${validateRef(ref)}:${path}`]));
  } catch {
    return undefined;
  }
}

function readBaseVersion(ref) {
  try {
    return parseStableVersion(git(["show", `${validateRef(ref)}:VERSION`]));
  } catch {
    const legacy = readJsonAtRef(ref, "frontend/package.json")?.version;
    if (!legacy) {
      throw new Error(`Base ${ref} has neither VERSION nor frontend/package.json version`);
    }
    return parseStableVersion(legacy);
  }
}

function readStagedVersion() {
  try {
    return git(["show", ":VERSION"]).trim();
  } catch {
    try {
      return git(["show", "HEAD:VERSION"]).trim();
    } catch {
      return readVersionRecords(ROOT).canonical;
    }
  }
}

function readStagedRecords() {
  function staged(path) {
    try {
      return git(["show", `:${path}`]);
    } catch {
      return git(["show", `HEAD:${path}`]);
    }
  }
  const packageJson = JSON.parse(staged("frontend/package.json"));
  const lockfile = JSON.parse(staged("frontend/package-lock.json"));
  return {
    canonical: staged("VERSION").trim(),
    package: packageJson.version,
    lockfile: lockfile.packages?.[""]?.version,
  };
}

function changedPaths(base, staged) {
  const args = staged
    ? ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"]
    : ["diff", "--name-only", "-z", "--diff-filter=ACMR", validateRef(base)];
  return git(args).split("\0").filter(Boolean);
}

function assertMirrors(records) {
  const values = new Set(Object.values(records));
  if (values.size !== 1) {
    throw new Error(
      `Version drift: VERSION=${records.canonical}, package=${records.package}, lockfile=${records.lockfile}`,
    );
  }
}

function assertTag(version) {
  if (process.env.GITHUB_REF_TYPE === "tag" && process.env.GITHUB_REF_NAME !== `v${version}`) {
    throw new Error(`Release tag must equal v${version}`);
  }
}

function runCheck(args) {
  const staged = args.includes("--staged");
  const base = resolveBase(args);
  const policy = readVersionPolicy(ROOT);
  const records = staged ? readStagedRecords() : readVersionRecords(ROOT);
  assertMirrors(records);
  const current = staged ? readStagedVersion() : records.canonical;
  const baseVersion = `${readBaseVersion(base).major}.${readBaseVersion(base).minor}.${readBaseVersion(base).patch}`;
  const paths = changedPaths(base, staged);
  if (!isSufficientVersion(baseVersion, current, paths, policy)) {
    throw new Error(`Protected changes require a version greater than ${baseVersion}; found ${current}`);
  }
  assertTag(current);
  console.log(current);
}

function runBump(args) {
  if (args.includes("--staged")) throw new Error("bump does not support --staged");
  const releases = ["major", "minor", "patch"].filter((name) => args.includes(`--${name}`));
  if (releases.length > 1) throw new Error("Choose only one of --patch, --minor, or --major");
  const release = releases[0] ?? "patch";
  const base = resolveBase(args);
  const policy = readVersionPolicy(ROOT);
  const records = readVersionRecords(ROOT);
  assertMirrors(records);
  const baseParsed = readBaseVersion(base);
  const baseVersion = `${baseParsed.major}.${baseParsed.minor}.${baseParsed.patch}`;
  const paths = changedPaths(base, false);

  if (isSufficientVersion(baseVersion, records.canonical, paths, policy)) {
    console.log(records.canonical);
    return;
  }

  const target = bumpVersion(baseVersion, release);
  if (compareVersions(target, records.canonical) < 0) {
    throw new Error(`Requested ${release} target ${target} would lower ${records.canonical}`);
  }
  writeVersionRecords(ROOT, target);
  console.log(target);
}

function main() {
  const [command = "check", ...args] = process.argv.slice(2);
  resolve(".");
  if (command === "print") {
    const records = readVersionRecords(ROOT);
    assertMirrors(records);
    console.log(records.canonical);
  } else if (command === "check") {
    runCheck(args);
  } else if (command === "bump") {
    runBump(args);
  } else {
    throw new Error(`Usage: node scripts/version.mjs <check|bump|print>`);
  }
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error(REMEDIATION);
  process.exitCode = 1;
}
