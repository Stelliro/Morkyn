/**
 * Playtest #2: saved presets with the same name got the exact same label.
 *
 * Saved "overpowered", then saved another: the list showed two identical
 * names. The player wants the first to keep the bare name, the next to be
 * "Name 1", then "Name 2", and a number freed by a delete to be the next one
 * handed out (no 1, 2, 3, 15, 17 gaps). Built-in names count as taken, and a
 * rename may keep its own name.
 *
 * Runs uniquePresetLabel from static/app.js against a stubbed preset list.
 *
 * Exit 0 = all cases pass
 * Exit 1 = a case failed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP_JS = path.join(path.resolve(__dirname, ".."), "static", "app.js");

let uniquePresetLabel;
const presets = [];
try {
  const source = fs.readFileSync(APP_JS, "utf8");
  const start = source.indexOf("\nfunction uniquePresetLabel(");
  const end = source.indexOf("\nfunction allDirectorPresets(", start);
  if (start < 0 || end < 0) throw new Error("uniquePresetLabel not found in app.js");
  const sandbox = { allDirectorPresets: () => presets.slice() };
  vm.createContext(sandbox);
  vm.runInContext(`${source.slice(start, end)}\nthis.uniquePresetLabel = uniquePresetLabel;`, sandbox);
  uniquePresetLabel = sandbox.uniquePresetLabel;
} catch (error) {
  console.error(`setup: ${error.message}`);
  process.exit(2);
}

let failed = 0;
function expect(name, actual, wanted) {
  if (actual === wanted) {
    console.log(`ok   ${name}`);
  } else {
    failed += 1;
    console.log(`FAIL ${name}: got "${actual}", wanted "${wanted}"`);
  }
}
let nextId = 0;
function save(label, options) {
  const stored = uniquePresetLabel(label, options);
  nextId += 1;
  presets.push({ id: `user_${nextId}`, label: stored, builtin: false });
  return stored;
}
function remove(label) {
  const i = presets.findIndex((p) => p.label === label);
  if (i >= 0) presets.splice(i, 1);
}

presets.push({ id: "op_mc", label: "Overpowered", builtin: true });

expect("first keeps the bare name", save("Night run"), "Night run");
expect("second is numbered 1", save("Night run"), "Night run 1");
expect("third is numbered 2", save("Night run"), "Night run 2");
expect("fourth is numbered 3", save("Night run"), "Night run 3");
remove("Night run 1");
expect("a deleted number is reused", save("Night run"), "Night run 1");
expect("then the next free one", save("Night run"), "Night run 4");
remove("Night run");
expect("a freed bare name is reused", save("Night run"), "Night run");
expect("typing a taken numbered name counts from the base", save("Night run 2"), "Night run 5");
expect("clash is case-insensitive", save("night RUN"), "night RUN 6");
expect("built-in name is taken", save("Overpowered"), "Overpowered 1");
expect("built-in clash, not a ' copy' suffix", save("Overpowered"), "Overpowered 2");
const renamed = presets.find((p) => p.label === "Overpowered 2");
expect("rename keeps its own name", uniquePresetLabel("Overpowered 2", { excludeId: renamed.id }), "Overpowered 2");
expect("rename into a clash is numbered", uniquePresetLabel("Night run", { excludeId: renamed.id }), "Night run 7");
expect("blank falls back", save("   "), "Saved setup");
expect("blank fallback is numbered too", save(""), "Saved setup 1");
const long = "x".repeat(40);
expect("first long name kept", save(long), long);
expect("numbered long name stays within 40", save(long), `${"x".repeat(38)} 1`);

if (failed) {
  console.log(`${failed} failed`);
  process.exit(1);
}
console.log("all passed");
