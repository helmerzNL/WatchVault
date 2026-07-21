import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import ts from "typescript";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_ROOT = resolve(SCRIPT_DIR, "..", "..");
const KINDS = ["route", "action", "permission", "scope", "preference", "locale", "theme", "state"];
const ACTION_METHODS = new Set(["post", "put", "patch", "del", "upload"]);
const THEMES = ["dark", "light", "system"];
const LOCALES = ["de", "en", "es", "fr", "it", "nl"];

function normalizePath(value) {
  return value.split(sep).join("/");
}

function safeRelativePath(value) {
  if (
    typeof value !== "string"
    || value.length === 0
    || isAbsolute(value)
    || /^[A-Za-z]:[\\/]/.test(value)
  ) {
    return false;
  }
  const parts = value.replaceAll("\\", "/").split("/");
  return !parts.includes("..") && !parts.includes("") && parts.every((part) => part !== ".");
}

function sourceFiles(root) {
  const base = resolve(root, "frontend", "src");
  if (!existsSync(base)) return [];
  const files = [];
  const walk = (directory) => {
    for (const name of readdirSync(directory).sort()) {
      const path = resolve(directory, name);
      const stat = statSync(path);
      if (stat.isDirectory()) walk(path);
      else if (
        /\.(?:ts|tsx)$/.test(name)
        && !normalizePath(relative(base, path)).startsWith("test/")
        && !name.endsWith(".test.ts")
        && !name.endsWith(".test.tsx")
      ) files.push(path);
    }
  };
  walk(base);
  return files;
}

function parseSource(path) {
  return ts.createSourceFile(
    path,
    readFileSync(path, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function jsxName(node) {
  return ts.isIdentifier(node.tagName) ? node.tagName.text : node.tagName.getText();
}

function jsxAttribute(node, name) {
  return node.attributes.properties.find(
    (attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText() === name,
  );
}

function attributeText(attribute, sourceFile) {
  if (!attribute?.initializer) return null;
  if (ts.isStringLiteral(attribute.initializer)) return attribute.initializer.text;
  if (
    ts.isJsxExpression(attribute.initializer)
    && attribute.initializer.expression
    && ts.isStringLiteralLike(attribute.initializer.expression)
  ) {
    return attribute.initializer.expression.text;
  }
  return attribute.initializer.getText(sourceFile);
}

function routeId(path) {
  if (path === "*") return "route.wildcard";
  return `route.${path.replace(/^\/+/, "").replace(/:[A-Za-z0-9_]+/g, "param").replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase()}`;
}

function endpointValue(node) {
  if (ts.isStringLiteralLike(node)) return node.text;
  if (ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) {
    let value = node.head.text;
    for (const span of node.templateSpans) value += ":param" + span.literal.text;
    return value;
  }
  return null;
}

function actionId(method, endpoint) {
  const slug = endpoint
    .replace(/:[A-Za-z0-9_.-]+/g, "param")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
  return `action.${method}.${slug}`;
}

function addCandidate(map, candidate) {
  const existing = map.get(candidate.id);
  if (!existing || candidate.source.path.localeCompare(existing.source.path) < 0) map.set(candidate.id, candidate);
}

function discoverTypeScript(root, candidates) {
  for (const absolutePath of sourceFiles(root)) {
    const sourceFile = parseSource(absolutePath);
    const path = normalizePath(relative(root, absolutePath));
    const text = sourceFile.getFullText();

    const visit = (node) => {
      if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && jsxName(node) === "Route") {
        const index = jsxAttribute(node, "index");
        const pathAttribute = jsxAttribute(node, "path");
        if (index) {
          addCandidate(candidates, {
            id: "route.index",
            kind: "route",
            value: "/",
            source: { path, anchor: index.getText(sourceFile) },
          });
        } else if (pathAttribute) {
          const value = attributeText(pathAttribute, sourceFile);
          if (value) {
            addCandidate(candidates, {
              id: routeId(value),
              kind: "route",
              value,
              source: { path, anchor: pathAttribute.getText(sourceFile) },
            });
          }
        }
      }

      if (ts.isInterfaceDeclaration(node) && node.name.text === "Prefs") {
        for (const member of node.members) {
          if (!ts.isPropertySignature(member) || !member.name) continue;
          const name = member.name.getText(sourceFile).replace(/[?'"]/g, "");
          addCandidate(candidates, {
            id: `preference.${name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").replaceAll("_", "-").toLowerCase()}`,
            kind: "preference",
            value: name,
            source: { path, anchor: member.getText(sourceFile).split(/\r?\n/, 1)[0] },
          });
          if (name === "theme" && member.type && ts.isUnionTypeNode(member.type)) {
            for (const type of member.type.types) {
              if (!ts.isLiteralTypeNode(type) || !ts.isStringLiteral(type.literal)) continue;
              addCandidate(candidates, {
                id: `theme.${type.literal.text}`,
                kind: "theme",
                value: type.literal.text,
                source: { path, anchor: type.literal.getText(sourceFile) },
              });
            }
          }
        }
      }

      if (ts.isVariableDeclaration(node) && node.name.getText(sourceFile) === "LANGUAGES" && node.initializer) {
        const array = ts.isArrayLiteralExpression(node.initializer)
          ? node.initializer
          : ts.isAsExpression(node.initializer) && ts.isArrayLiteralExpression(node.initializer.expression)
            ? node.initializer.expression
            : null;
        for (const element of array?.elements ?? []) {
          if (!ts.isObjectLiteralExpression(element)) continue;
          const code = element.properties.find(
            (property) => ts.isPropertyAssignment(property) && property.name.getText(sourceFile) === "code",
          );
          if (!code || !ts.isPropertyAssignment(code) || !ts.isStringLiteralLike(code.initializer)) continue;
          const value = code.initializer.text;
          addCandidate(candidates, {
            id: `locale.${value}`,
            kind: "locale",
            value,
            source: { path, anchor: element.getText(sourceFile) },
          });
        }
      }

      if (
        ts.isCallExpression(node)
        && ts.isPropertyAccessExpression(node.expression)
        && ts.isIdentifier(node.expression.expression)
        && node.expression.expression.text === "api"
        && ACTION_METHODS.has(node.expression.name.text)
        && node.arguments[0]
      ) {
        const endpoint = endpointValue(node.arguments[0]);
        if (endpoint) {
          const method = node.expression.name.text;
          addCandidate(candidates, {
            id: actionId(method, endpoint),
            kind: "action",
            value: `${method.toUpperCase()} ${endpoint}`,
            source: { path, anchor: node.arguments[0].getText(sourceFile) },
          });
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(sourceFile);

    if (path === "frontend/src/App.tsx") {
      const appStates = [
        ["state.app-loading", "loading", "<Loading />"],
        ["state.auth-unauthenticated", "unauthenticated", "<Login />"],
        ["state.auth-authenticated", "authenticated", "<Routes>"],
      ];
      for (const [id, value, anchor] of appStates) {
        if (text.includes(anchor)) addCandidate(candidates, { id, kind: "state", value, source: { path, anchor } });
      }
    }
    if (path === "frontend/src/lib/app.tsx" && text.includes("scope: string;")) {
      addCandidate(candidates, {
        id: "scope.household",
        kind: "scope",
        value: "all",
        source: { path, anchor: "scope: string; // 'all' or a user id" },
      });
      addCandidate(candidates, {
        id: "scope.personal",
        kind: "scope",
        value: "user-id",
        source: { path, anchor: "scope: string; // 'all' or a user id" },
      });
    }
  }
}

function discoverPermissions(root, candidates) {
  const path = "backend/migrations/0002_rbac_prefs.sql";
  const absolutePath = resolve(root, path);
  if (!existsSync(absolutePath)) return;
  const text = readFileSync(absolutePath, "utf8");
  for (const match of text.matchAll(/\('([a-z][a-z0-9.]+)',\s+'([^']+)'\)/g)) {
    const value = match[1];
    if (!value.includes(".")) continue;
    addCandidate(candidates, {
      id: `permission.${value.replaceAll(".", "-")}`,
      kind: "permission",
      value,
      source: { path, anchor: `'${value}'` },
    });
  }
}

function discoverImportantStates(root, candidates) {
  const states = [
    ["state.loading", "loading", "frontend/src/components/ui.tsx", "export function Loading"],
    ["state.empty", "empty", "frontend/src/components/ui.tsx", "export function Empty"],
    ["state.error", "error", "frontend/src/components/ui.tsx", "export function ErrorState"],
    ["state.partial", "partial", "frontend/src/pages/Dashboard.tsx", "providers.loading ?"],
    ["state.forbidden", "forbidden", "frontend/src/pages/TitleDetail.tsx", "const canEdit = can(\"ingest.write\");"],
    ["state.pending", "pending", "frontend/src/pages/TitleDetail.tsx", "disabled={busy"],
    ["state.success", "success", "frontend/src/lib/app.tsx", "const toast = useCallback"],
  ];
  for (const [id, value, path, anchor] of states) {
    const absolutePath = resolve(root, path);
    if (existsSync(absolutePath) && readFileSync(absolutePath, "utf8").includes(anchor)) {
      addCandidate(candidates, { id, kind: "state", value, source: { path, anchor } });
    }
  }
}

export function discoverCapabilities(root = DEFAULT_ROOT) {
  const candidates = new Map();
  discoverTypeScript(root, candidates);
  discoverPermissions(root, candidates);
  discoverImportantStates(root, candidates);
  return [...candidates.values()].sort((a, b) => a.id.localeCompare(b.id));
}

function schemaValidator(root) {
  const schemaPath = resolve(root, "capabilities", "schema.json");
  const schema = existsSync(schemaPath)
    ? JSON.parse(readFileSync(schemaPath, "utf8"))
    : JSON.parse(readFileSync(resolve(DEFAULT_ROOT, "capabilities", "schema.json"), "utf8"));
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  return ajv.compile(schema);
}

function requirementMap(root) {
  const path = resolve(root, ".planning", "REQUIREMENTS.md");
  const map = new Map();
  if (!existsSync(path)) return map;
  const text = readFileSync(path, "utf8");
  for (const match of text.matchAll(/\|\s*([A-Z]+-\d{2})\s*\|\s*Phase\s+(\d+)\s*\|/g)) {
    map.set(match[1], Number(match[2]));
  }
  return map;
}

export function validateInventory(inventory, options = {}) {
  const root = options.root ?? DEFAULT_ROOT;
  const errors = [];
  const validate = schemaValidator(root);
  if (!validate(inventory)) {
    for (const error of validate.errors ?? []) errors.push(`schema ${error.instancePath || "/"} ${error.message}`);
  }
  if (!Array.isArray(inventory)) {
    throw new Error(`Capability inventory validation failed:\n- ${errors.join("\n- ") || "inventory must be an array"}`);
  }
  if (inventory.length === 0) errors.push("inventory must not be empty");

  const ids = new Set();
  const requirements = options.requirements instanceof Set
    ? new Map([...options.requirements].map((id) => [id, null]))
    : options.requirements instanceof Map
      ? options.requirements
      : requirementMap(root);

  for (const [index, item] of inventory.entries()) {
    if (!item || typeof item !== "object") continue;
    if (ids.has(item.id)) errors.push(`duplicate capability ID: ${item.id}`);
    ids.add(item.id);
    if (item.kind && item.id && !item.id.startsWith(`${item.kind}.`)) {
      errors.push(`${item.id}: ID prefix must match kind ${item.kind}`);
    }
    const sourcePath = item.source?.path;
    if (!safeRelativePath(sourcePath)) {
      errors.push(`${item.id ?? `item ${index}`}: invalid or traversal source path`);
      continue;
    }
    const absolutePath = resolve(root, sourcePath);
    if (!existsSync(absolutePath)) errors.push(`${item.id}: source path does not exist: ${sourcePath}`);
    else if (item.source?.anchor && !readFileSync(absolutePath, "utf8").includes(item.source.anchor)) {
      errors.push(`${item.id}: source anchor not found in ${sourcePath}: ${item.source.anchor}`);
    }
    if (requirements.size > 0 && item.owner?.requirement) {
      if (!requirements.has(item.owner.requirement)) errors.push(`${item.id}: unknown requirement ${item.owner.requirement}`);
      else {
        const expectedPhase = requirements.get(item.owner.requirement);
        if (expectedPhase !== null && expectedPhase !== item.owner.phase) {
          errors.push(`${item.id}: requirement ${item.owner.requirement} belongs to phase ${expectedPhase}, not ${item.owner.phase}`);
        }
      }
    }
  }

  if (inventory.every((item) => item?.owner && typeof item.id === "string")) {
    const actualOrder = inventory.map(({ id }) => id);
    const expectedOrder = canonicalSort(inventory).map(({ id }) => id);
    if (actualOrder.some((id, index) => id !== expectedOrder[index])) {
      errors.push("inventory records must use canonical phase, requirement, kind, and ID ordering");
    }
  }

  if (options.discovered) {
    const discoveredIds = new Set(options.discovered.map(({ id }) => id));
    const missing = [...discoveredIds].filter((id) => !ids.has(id)).sort();
    const extra = [...ids].filter((id) => !discoveredIds.has(id)).sort();
    if (missing.length) errors.push(`missing discovered capability IDs: ${missing.join(", ")}`);
    if (extra.length) errors.push(`inventory IDs without discovery candidates: ${extra.join(", ")}`);
  }

  if (errors.length) throw new Error(`Capability inventory validation failed:\n- ${errors.join("\n- ")}`);
  return inventory;
}

export function canonicalSort(inventory) {
  return [...inventory].sort((a, b) =>
    a.owner.phase - b.owner.phase
    || a.owner.requirement.localeCompare(b.owner.requirement)
    || KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind)
    || a.id.localeCompare(b.id));
}

function markdownCell(value) {
  return String(value).replaceAll("|", "\\|").replaceAll("\r", "").replaceAll("\n", " ");
}

export function renderCapabilitiesMarkdown(inventory) {
  const lines = [
    "# WatchVault Capability Inventory",
    "",
    "> Generated from `capabilities/inventory.json`. Do not edit this file directly.",
    "",
    `**Capabilities:** ${inventory.length}`,
    "",
    "| Phase | Requirement | Kind | Capability | Current behavior | Dimensions | Source | Evidence |",
    "|---:|---|---|---|---|---|---|---|",
  ];
  for (const item of canonicalSort(inventory)) {
    const dimensions = Object.entries(item.dimensions)
      .map(([key, values]) => `${key}: ${values.join(", ")}`)
      .join("; ");
    lines.push(
      `| ${item.owner.phase} | ${item.owner.requirement} | ${item.kind} | \`${item.id}\` | ${markdownCell(item.behavior)} | ${markdownCell(dimensions)} | \`${item.source.path}\` — \`${markdownCell(item.source.anchor)}\` | ${item.evidence.map((value) => `\`${markdownCell(value)}\``).join("<br>")} |`,
    );
  }
  return `${lines.join("\n")}\n`;
}

function readInventory(root) {
  const path = resolve(root, "capabilities", "inventory.json");
  if (!existsSync(path)) throw new Error(`Capability inventory is missing: ${normalizePath(relative(root, path))}`);
  return JSON.parse(readFileSync(path, "utf8"));
}

function check(root) {
  const inventory = readInventory(root);
  const discovered = discoverCapabilities(root);
  validateInventory(inventory, { root, discovered });
  const expected = renderCapabilitiesMarkdown(inventory);
  const reportPath = resolve(root, "docs", "CAPABILITIES.md");
  if (!existsSync(reportPath) || readFileSync(reportPath, "utf8") !== expected) {
    throw new Error("Generated capability report is stale. Run: node frontend/scripts/capabilities.mjs generate");
  }
  process.stdout.write(`Capability inventory valid: ${inventory.length} records, ${discovered.length} discovery candidates.\n`);
}

function generate(root) {
  const inventory = readInventory(root);
  validateInventory(inventory, { root, discovered: discoverCapabilities(root) });
  const path = resolve(root, "docs", "CAPABILITIES.md");
  writeFileSync(path, renderCapabilitiesMarkdown(inventory), "utf8");
  process.stdout.write(`Generated ${normalizePath(relative(root, path))}.\n`);
}

function main() {
  const command = process.argv[2] ?? "check";
  if (command === "discover") {
    process.stdout.write(`${JSON.stringify(discoverCapabilities(DEFAULT_ROOT), null, 2)}\n`);
  } else if (command === "generate") {
    generate(DEFAULT_ROOT);
  } else if (command === "check") {
    check(DEFAULT_ROOT);
  } else {
    throw new Error(`Unknown capability command: ${command}. Use check, generate, or discover.`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

export const catalogs = Object.freeze({ kinds: KINDS, themes: THEMES, locales: LOCALES });
