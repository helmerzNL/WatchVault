import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { generateManifest } from "../ci/baseline-manifest.mjs";

test("baseline manifest records pinned provenance and deterministic image hashes", () => {
  const root = mkdtempSync(join(tmpdir(), "watchvault-baselines-"));
  const screenshots = join(root, "screenshots");
  const output = join(root, "manifest.json");
  mkdirSync(screenshots);
  try {
    for (let index = 1; index <= 16; index += 1) {
      writeFileSync(join(screenshots, `${String(index).padStart(2, "0")}.png`), `png-${index}`);
    }
    const sourceCommit = "a".repeat(40);
    const options = {
      screenshotRoot: screenshots,
      output,
      manifestBase: root,
      sourceCommit,
      container: "mcr.microsoft.com/playwright:v1.61.1-noble",
    };
    const first = generateManifest(options);
    const firstBytes = readFileSync(output);
    const second = generateManifest(options);
    assert.deepEqual(second, first);
    assert.deepEqual(readFileSync(output), firstBytes);
    assert.equal(first.source_commit, sourceCommit);
    assert.equal(first.playwright_version, "1.61.1");
    assert.equal(first.image_count, 16);
    assert.equal(first.images.length, 16);
    assert.ok(first.images.every((image) => /^[0-9a-f]{64}$/.test(image.sha256)));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("baseline manifest rejects incomplete image sets and unsafe provenance", () => {
  const root = mkdtempSync(join(tmpdir(), "watchvault-baselines-"));
  const screenshots = join(root, "screenshots");
  mkdirSync(screenshots);
  try {
    writeFileSync(join(screenshots, "only.png"), "png");
    assert.throws(
      () => generateManifest({
        screenshotRoot: screenshots,
        output: join(root, "manifest.json"),
        manifestBase: root,
        sourceCommit: "not-a-sha",
        container: "pinned",
      }),
      /commit SHA/i,
    );
    assert.throws(
      () => generateManifest({
        screenshotRoot: screenshots,
        output: join(root, "manifest.json"),
        manifestBase: root,
        sourceCommit: "b".repeat(40),
        container: "pinned",
      }),
      /Expected 16/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
