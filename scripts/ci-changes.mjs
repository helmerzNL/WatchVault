#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const versionPolicy = JSON.parse(readFileSync(resolve(ROOT, "version-policy.json"), "utf8"));

const fullSuitePrefixes = [
  ".github/workflows/",
  "deploy/",
  "scripts/",
  "frontend/e2e/fixtures/",
  "frontend/src/test/",
];
const fullSuiteFiles = new Set([
  "Dockerfile",
  "docker-compose.yml",
  "docker-compose.build.yml",
  "version-policy.json",
]);

function assertSafePath(path) {
  if (
    typeof path !== "string"
    || path.length === 0
    || path.includes("\\")
    || path.includes("\0")
    || isAbsolute(path)
  ) {
    throw new Error(`Unsafe changed path: ${JSON.stringify(path)}`);
  }
  const segments = path.split("/");
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    throw new Error(`Changed path traversal is not allowed: ${path}`);
  }
}

function matchesPolicyPattern(path, pattern) {
  if (pattern.endsWith("/**")) return path.startsWith(pattern.slice(0, -2));
  return path === pattern;
}

function isPolicyProtected(path) {
  const included = versionPolicy.include.some((pattern) => matchesPolicyPattern(path, pattern));
  const excluded = versionPolicy.exclude.some((pattern) => {
    if (pattern.endsWith("/**/*.md")) {
      return path.startsWith(pattern.slice(0, -7)) && path.endsWith(".md");
    }
    return matchesPolicyPattern(path, pattern);
  });
  return included && !excluded;
}

function classifyPath(path) {
  assertSafePath(path);

  if (fullSuiteFiles.has(path) || fullSuitePrefixes.some((prefix) => path.startsWith(prefix))) {
    return { backend: true, frontend: true, browser: true, reason: `${path}: full-suite surface` };
  }
  if (path.startsWith("backend/") || path.startsWith("plugins/")) {
    return { backend: true, frontend: false, browser: true, reason: `${path}: API/auth surface` };
  }
  if (path.startsWith("frontend/")) {
    return { backend: false, frontend: true, browser: true, reason: `${path}: frontend surface` };
  }
  if (path.startsWith("homeassistant/")) {
    return { backend: false, frontend: false, browser: false, reason: `${path}: Home Assistant only` };
  }
  if (
    path.endsWith(".md")
    || path.endsWith(".txt")
    || path.startsWith("docs/")
    || path.startsWith(".planning/")
    || path === "LICENSE"
  ) {
    return { backend: false, frontend: false, browser: false, reason: `${path}: documentation only` };
  }
  if (isPolicyProtected(path)) {
    throw new Error(`Protected path has no CI classification: ${path}`);
  }
  return { backend: true, frontend: true, browser: true, reason: `${path}: unknown surface fails closed` };
}

function assertSafeRef(event, ref) {
  if (event === "pull_request" && /^refs\/pull\/\d+\/merge$/.test(ref)) return;
  if (event === "push" && (ref === "refs/heads/main" || /^refs\/tags\/v[^/]+$/.test(ref))) return;
  if (event === "workflow_dispatch" && /^refs\/(heads|tags)\/[A-Za-z0-9._/-]+$/.test(ref)) return;
  throw new Error(`Unsupported or unsafe ${event} ref: ${ref}`);
}

export function selectJobs({ event, ref, paths }) {
  if (!["pull_request", "push", "workflow_dispatch"].includes(event)) {
    throw new Error(`Unsupported CI event: ${event}`);
  }
  assertSafeRef(event, ref);
  if (!Array.isArray(paths)) throw new Error("Changed paths must be an array");

  if (event !== "pull_request") {
    return {
      version: true,
      inventory: true,
      backend: true,
      frontend: true,
      browser: true,
      reasons: [`${event} ${ref} forces full suite`],
    };
  }
  if (paths.length === 0) {
    return {
      version: true,
      inventory: true,
      backend: false,
      frontend: false,
      browser: false,
      reasons: ["no changed paths"],
    };
  }

  const classifications = [...new Set(paths)].sort().map(classifyPath);
  return {
    version: true,
    inventory: true,
    backend: classifications.some((item) => item.backend),
    frontend: classifications.some((item) => item.frontend),
    browser: classifications.some((item) => item.browser),
    reasons: classifications.map((item) => item.reason),
  };
}

function changedPaths(base, head) {
  if (!/^[0-9a-f]{40}$/i.test(base) || !/^[0-9a-f]{40}$/i.test(head)) {
    throw new Error("BASE_SHA and HEAD_SHA must be full Git commit SHAs");
  }
  const result = spawnSync("git", ["diff", "--name-only", "-z", `${base}...${head}`], {
    cwd: ROOT,
    encoding: "utf8",
    shell: false,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim() || "git diff failed");
  return result.stdout.split("\0").filter(Boolean);
}

function writeOutputs(selection) {
  const output = process.env.GITHUB_OUTPUT;
  if (!output) throw new Error("GITHUB_OUTPUT is required");
  const lines = ["version", "inventory", "backend", "frontend", "browser"]
    .map((key) => `${key}=${selection[key]}`);
  lines.push(`reasons=${JSON.stringify(selection.reasons)}`);
  appendFileSync(output, `${lines.join("\n")}\n`, "utf8");
}

function main() {
  const event = process.env.GITHUB_EVENT_NAME;
  const ref = process.env.GITHUB_REF;
  if (!event || !ref) throw new Error("GITHUB_EVENT_NAME and GITHUB_REF are required");
  const paths = event === "pull_request"
    ? changedPaths(process.env.BASE_SHA ?? "", process.env.HEAD_SHA ?? "")
    : [];
  writeOutputs(selectJobs({ event, ref, paths }));
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
