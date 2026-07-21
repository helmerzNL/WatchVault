#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";

import { formatVersion, parseStableVersion } from "./lib/version-policy.mjs";

const root = process.cwd();

function canonicalVersion() {
  return formatVersion(parseStableVersion(readFileSync(join(root, "VERSION"), "utf8")));
}

function main() {
  const [command, ...args] = process.argv.slice(2);
  const version = canonicalVersion();
  const configured = process.env.WATCHVAULT_VERSION;
  if (configured && configured !== version) {
    throw new Error(`WATCHVAULT_VERSION=${configured} conflicts with VERSION=${version}`);
  }

  if (command === "print") {
    console.log(version);
    return;
  }
  if (command !== "compose") {
    throw new Error("Usage: node scripts/docker-version.mjs <print|compose ...args>");
  }

  const result = spawnSync(
    "docker",
    ["compose", "-f", "docker-compose.yml", "-f", "docker-compose.build.yml", ...args],
    {
      cwd: root,
      env: { ...process.env, WATCHVAULT_VERSION: version },
      shell: false,
      stdio: "inherit",
    },
  );
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
