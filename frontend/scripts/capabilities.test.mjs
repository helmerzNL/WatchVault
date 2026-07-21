import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  canonicalSort,
  discoverCapabilities,
  renderCapabilitiesMarkdown,
  validateInventory,
} from "./capabilities.mjs";

function entry(overrides = {}) {
  return {
    id: "route.dashboard",
    kind: "route",
    source: { path: "frontend/src/App.tsx", anchor: "/dashboard" },
    behavior: "Authenticated users can open the dashboard.",
    dimensions: {
      permissions: ["authenticated"],
      scopes: ["personal", "household"],
      themes: ["dark", "light", "system"],
      locales: ["en"],
      states: ["loading", "success", "error"],
    },
    owner: { requirement: "REFJ-01", phase: 5 },
    evidence: ["frontend/e2e/reference-journey.spec.ts"],
    ...overrides,
  };
}

function fixtureRoot() {
  const root = mkdtempSync(join(tmpdir(), "watchvault-capabilities-"));
  mkdirSync(join(root, "frontend", "src"), { recursive: true });
  writeFileSync(
    join(root, "frontend", "src", "App.tsx"),
    'const path = "/dashboard";\nconst theme = "system";\n',
  );
  return root;
}

test("strict validation rejects null empty unknown fields and duplicate IDs", () => {
  const root = fixtureRoot();
  assert.throws(() => validateInventory(null, { root }), /inventory/i);
  assert.throws(() => validateInventory([], { root }), /empty/i);
  assert.throws(
    () => validateInventory([{ ...entry(), unknown: true }], { root }),
    /additional|unknown/i,
  );
  assert.throws(() => validateInventory([entry(), entry()], { root }), /duplicate/i);
});

test("distinct atomic IDs remain separate while identical IDs collide", () => {
  const root = fixtureRoot();
  const inventory = [
    entry(),
    entry({ id: "action.dashboard.refresh", kind: "action", behavior: "Refresh dashboard data." }),
  ];
  assert.equal(validateInventory(inventory, { root }).length, 2);
  assert.throws(() => validateInventory([entry(), entry()], { root }), /duplicate/i);
});

test("source paths and anchors must resolve inside the repository", () => {
  const root = fixtureRoot();
  assert.throws(
    () => validateInventory([entry({ source: { path: "../secret", anchor: "x" } })], { root }),
    /path|traversal/i,
  );
  assert.throws(
    () => validateInventory([entry({ source: { path: "frontend/src/App.tsx", anchor: "missing" } })], { root }),
    /anchor/i,
  );
});

test("ownership and evidence are required and requirement references must resolve", () => {
  const root = fixtureRoot();
  assert.throws(
    () => validateInventory([entry({ evidence: [] })], { root }),
    /evidence/i,
  );
  assert.throws(
    () => validateInventory([entry({ owner: { requirement: "UNKNOWN-01", phase: 5 } })], {
      root,
      requirements: new Set(["REFJ-01"]),
    }),
    /requirement/i,
  );
});

test("discovery and inventory sets must match exactly including singleton catalogs", () => {
  const root = fixtureRoot();
  const discovered = discoverCapabilities(root);
  assert.ok(discovered.some((item) => item.value === "/dashboard"));
  assert.ok(discovered.some((item) => item.value === "system"));
});

test("canonical ordering is phase requirement kind then stable ID", () => {
  const values = [
    entry({ id: "z", kind: "route", owner: { requirement: "REFJ-02", phase: 5 } }),
    entry({ id: "b", kind: "action" }),
    entry({ id: "a", kind: "action" }),
  ];
  assert.deepEqual(canonicalSort(values).map(({ id }) => id), ["a", "b", "z"]);
});

test("generated Markdown is deterministic UTF-8 LF with a final newline", () => {
  const inventory = [entry()];
  const first = renderCapabilitiesMarkdown(inventory);
  const second = renderCapabilitiesMarkdown([...inventory]);
  assert.equal(first, second);
  assert.equal(first.endsWith("\n"), true);
  assert.equal(first.includes("\r"), false);
  assert.match(first, /route\.dashboard/);
  assert.match(first, /REFJ-01/);
});
