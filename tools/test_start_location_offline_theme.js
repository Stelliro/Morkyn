/**
 * Regression: the offline start_location picker must not be genre-blind.
 *
 * `RANDOM_SETUP` in static/app.js held one flat, fantasy-leaning
 * start_location list -- and held it TWICE, under the same key in the same
 * object literal, so JavaScript kept the second and the first twelve names
 * never ran at all. Nobody had looked at this pool in a long time.
 *
 * Either way, a player randomizing a space opera while the server or model was
 * unavailable got "Mosswake Gate", "Sect Outer Court Gate" or "Ferry Landing
 * Stone" -- the same fantasy gate-town the shipped default used to hand every
 * world, arriving by a different road.
 *
 * The banks are now keyed by theme and `detectStartLocationTheme()` mirrors
 * `detect_location_theme()` in app/setup_composer.py. This harness locks the
 * mirror: same setting text in, same theme family out.
 *
 * Exit 0 = every setting picks from its own bank; no duplicate key
 * Exit 1 = a case regressed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

function extractFunction(source, name) {
  const start = source.indexOf(`
function ${name}(`);
  if (start < 0) throw new Error(`function ${name} not found in app.js`);
  let i = source.indexOf("{", start);
  let depth = 0;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

function extractConst(source, name) {
  const start = source.indexOf(`\nconst ${name} = `);
  if (start < 0) throw new Error(`const ${name} not found in app.js`);
  // Single-line declarations (regex literals, `new Map()`) carry no brackets
  // to walk, so take the whole line.
  const lineEnd = source.indexOf("\n", start + 1);
  const firstLine = source.slice(start, lineEnd);
  if (/;\s*$/.test(firstLine)) return firstLine;
  let i = source.indexOf("=", start);
  let depth = 0;
  let started = false;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{" || ch === "[") { depth += 1; started = true; }
    else if (ch === "}" || ch === "]") {
      depth -= 1;
      if (started && depth === 0) return source.slice(start, i + 2);
    }
  }
  throw new Error(`unbalanced brackets extracting ${name}`);
}

const source = fs.readFileSync(APP_JS, "utf8");

let failures = 0;
function check(label, ok, detail) {
  if (ok) return;
  failures += 1;
  console.log(`  FAIL ${label}${detail ? ` -- ${detail}` : ""}`);
}

// --- the duplicate key that made half the old pool dead ------------------
{
  const start = source.indexOf("const RANDOM_SETUP = {");
  if (start < 0) { console.log("RANDOM_SETUP not found"); process.exit(2); }
  const lines = source.slice(start).split("\n");
  let depth = 0;
  const seen = new Map();
  for (let i = 0; i < lines.length; i += 1) {
    depth += (lines[i].match(/\{/g) || []).length - (lines[i].match(/\}/g) || []).length;
    const m = /^  ([A-Za-z_][A-Za-z0-9_]*):/.exec(lines[i]);
    if (m) seen.set(m[1], (seen.get(m[1]) || 0) + 1);
    if (depth === 0 && i > 0) break;
  }
  const dupes = [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k);
  check("RANDOM_SETUP has no duplicate keys", dupes.length === 0, dupes.join(", "));
}

// --- the offline picker resolves in genre --------------------------------
const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext(
  [
    extractConst(source, "START_LOCATION_BANKS"),
    extractConst(source, "START_LOCATION_THEME_KEYWORDS"),
    extractConst(source, "NEGATED_GENRE_WORD_RE"),
    extractConst(source, "THEME_KEYWORD_RE_CACHE"),
    extractFunction(source, "stripNegatedGenreWords"),
    extractFunction(source, "themeKeywordPresent"),
    // `const` in a vm script is a lexical binding, not a sandbox property.
    "this.__banks = START_LOCATION_BANKS;",
    "this.__keywords = START_LOCATION_THEME_KEYWORDS;",
    "this.__strip = stripNegatedGenreWords;",
    "this.__present = themeKeywordPresent;",
  ].join("\n\n"),
  sandbox,
);

const BANKS = sandbox.__banks;
const KEYWORDS = sandbox.__keywords;

/** The body of detectStartLocationTheme(), fed text directly. */
function themeFor(text) {
  const low = sandbox.__strip(String(text || "").toLowerCase());
  for (const [theme, keys] of KEYWORDS) {
    if (keys.some((k) => sandbox.__present(k, low))) return theme;
  }
  return "generic";
}

// Same settings the server-side matrix uses, so the two stay in step.
const CASES = [
  ["grounded medieval realism, no magic", "fantasy"],
  ["high fantasy with open magic and old empires", "fantasy"],
  ["far-future interstellar civilisation, faster-than-light travel, no magic", "space"],
  ["near-future cyberpunk megacity, corporate rule, street-level crime", "cyberpunk"],
  ["post-collapse wasteland eighty years after the grid died", "wasteland"],
  ["1880s frontier west with quiet, unexplained wrongness", "fantasy"],
  ["a galaxy of trade routes and old warships", "space"],
  ["the wastes, eighty years after the bombs", "wasteland"],
  ["megacorp arcology with chrome implants", "cyberpunk"],
  // Old empires collapse in fantasy; this must not read as a wasteland.
  ["after the collapse of the old empire, knights and ruins", "fantasy"],
  ["a dying king, three heirs, and no good options", "fantasy"],
  ["a mage academy where the faculty are the danger", "fantasy"],
  // "picking" contains "king"; "no magic" is not a vote for magic.
  ["derelict salvage crews picking over dead warships", "generic"],
  ["a heist crew in a modern city, no magic", "generic"],
  ["historical fiction, no fantasy at all, Edo period", "generic"],
  // Genres with no bank of their own get a placeless name, not a fantasy one.
  ["superheroes, street level, municipal politics", "generic"],
  ["high school slice of life with a supernatural secret", "generic"],
];

console.log("offline start_location picker:");
for (const [style, want] of CASES) {
  const got = themeFor(style);
  check(`theme for ${JSON.stringify(style.slice(0, 46))}`, got === want, `want ${want}, got ${got}`);
  const bank = BANKS[got];
  check(`bank exists for ${got}`, Array.isArray(bank) && bank.length > 0);
  console.log(`  ${got.padEnd(10)} ${style.slice(0, 52)}`);
}

// No bank may borrow another's names -- that is the whole point.
{
  const fantasy = new Set(BANKS.fantasy || []);
  for (const [theme, names] of Object.entries(BANKS)) {
    if (theme === "fantasy") continue;
    const borrowed = (names || []).filter((n) => fantasy.has(n));
    check(`${theme} bank has no fantasy names`, borrowed.length === 0, borrowed.join(", "));
  }
}

// Every theme the keyword table can return must have somewhere to draw from.
for (const [theme] of KEYWORDS) {
  check(`keyword theme ${theme} has a bank`, Array.isArray(BANKS[theme]) && BANKS[theme].length > 0);
}

if (failures) {
  console.log(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log("\nall offline start_location cases pick in genre");
process.exit(0);
