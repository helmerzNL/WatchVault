#!/usr/bin/env node
import { createHash } from "node:crypto";
import {
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_SCREENSHOT_ROOT = resolve(ROOT, "frontend/e2e/__screenshots__");
const DEFAULT_OUTPUT = resolve(ROOT, "frontend/playwright-baseline-manifest.json");
const EXPECTED_IMAGE_COUNT = 16;

function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const path = resolve(directory, entry.name);
      return entry.isDirectory() ? filesUnder(path) : [path];
    });
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function generateManifest({
  screenshotRoot = DEFAULT_SCREENSHOT_ROOT,
  output = DEFAULT_OUTPUT,
  manifestBase = resolve(ROOT, "frontend"),
  sourceCommit,
  container,
  expectedImageCount = EXPECTED_IMAGE_COUNT,
} = {}) {
  if (!/^[0-9a-f]{40}$/i.test(sourceCommit ?? "")) {
    throw new Error("SOURCE_COMMIT must be a full Git commit SHA");
  }
  if (typeof container !== "string" || container.length === 0) {
    throw new Error("PLAYWRIGHT_CONTAINER is required");
  }

  const frontendPackage = JSON.parse(
    readFileSync(resolve(ROOT, "frontend/package.json"), "utf8"),
  );
  const playwrightVersion = frontendPackage.devDependencies?.["@playwright/test"];
  if (!/^\d+\.\d+\.\d+$/.test(playwrightVersion ?? "")) {
    throw new Error("Frontend @playwright/test must be pinned to an exact version");
  }

  const images = filesUnder(screenshotRoot)
    .filter((path) => path.toLowerCase().endsWith(".png"))
    .sort()
    .map((path) => {
      const manifestPath = relative(manifestBase, path).split(sep).join("/");
      if (manifestPath.startsWith("../") || manifestPath === "..") {
        throw new Error(`Baseline image is outside manifest root: ${path}`);
      }
      return {
        path: manifestPath,
        sha256: sha256(path),
        bytes: statSync(path).size,
      };
    });
  if (images.length !== expectedImageCount) {
    throw new Error(`Expected ${expectedImageCount} baseline PNGs, found ${images.length}`);
  }

  const manifest = {
    schema_version: 1,
    source_commit: sourceCommit.toLowerCase(),
    playwright_version: playwrightVersion,
    container,
    image_count: images.length,
    images,
  };
  writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return manifest;
}

function main() {
  const manifest = generateManifest({
    sourceCommit: process.env.SOURCE_COMMIT,
    container: process.env.PLAYWRIGHT_CONTAINER,
  });
  console.log(`Baseline manifest valid: ${manifest.image_count} images for ${manifest.source_commit}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
