/**
 * Checking a LoRA must not mark engine prompts hand-edited.
 *
 * syncLorasIntoEnginePrompts writes face/body prompts then dispatched a bubbling
 * `input` event. Those textareas have data-engine-prompt, so the document
 * listener calls markEnginePromptDirty. rebuildEnginePrompts({ force: false })
 * (Auto update) then skips non-empty dirty fields — identity edits stop landing
 * after the first LoRA sync. Rebuild itself clears dirty and then calls sync,
 * which set dirty again.
 *
 * Exit 0 when the LoRA sync does not dispatch `input`.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");

function extractFunction(name) {
  const needle = `function ${name}(`;
  const start = src.indexOf(needle);
  if (start < 0) throw new Error(`missing ${name}`);
  let paren = 0;
  let body = -1;
  for (let i = start + needle.length - 1; i < src.length; i += 1) {
    const c = src[i];
    if (c === "(") paren += 1;
    else if (c === ")") {
      paren -= 1;
      if (paren === 0) {
        body = src.indexOf("{", i);
        break;
      }
    }
  }
  if (body < 0) throw new Error(`no body ${name}`);
  let depth = 0;
  for (let j = body; j < src.length; j += 1) {
    const c = src[j];
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(start, j + 1);
    }
  }
  throw new Error(`unclosed ${name}`);
}

function assert(cond, message) {
  if (!cond) {
    console.error("FAIL:", message);
    process.exitCode = 1;
  }
}

const sync = extractFunction("syncLorasIntoEnginePrompts");
const rebuild = extractFunction("rebuildEnginePrompts");
const mark = extractFunction("markEnginePromptDirty");

assert(
  !/dispatchEvent\s*\(\s*new Event\(\s*["']input["']/.test(sync),
  "syncLorasIntoEnginePrompts dispatches input, which marks engine prompts dirty",
);
assert(
  /data-engine-prompt/.test(src) && /markEnginePromptDirty\(/.test(src),
  "dirty marker for data-engine-prompt input is missing (test setup)",
);
assert(
  /enginePromptDirty\.face/.test(rebuild) && /syncLorasIntoEnginePrompts\(/.test(rebuild),
  "rebuild no longer gates on enginePromptDirty or no longer re-syncs LoRAs",
);
const clearAt = rebuild.indexOf("enginePromptDirty.face = false");
const syncAt = rebuild.indexOf("syncLorasIntoEnginePrompts(");
assert(clearAt >= 0 && syncAt > clearAt, "LoRA re-sync must run after rebuild clears dirty");
assert(/enginePromptDirty\[key\] = true/.test(mark), "markEnginePromptDirty no longer sets the flag");

// State machine of Auto update after a LoRA sync that changes prompt text.
function autoUpdateApplies(dirty, value, force = false) {
  return force || !dirty || !String(value || "").trim();
}
const dirtyAfterProgrammaticSync = /dispatchEvent\s*\(\s*new Event\(\s*["']input["']/.test(sync);
const prompt = "1girl, <lora:age_slider:1>";
assert(
  autoUpdateApplies(dirtyAfterProgrammaticSync, prompt, false) === true,
  "auto-update would skip a non-empty prompt after LoRA sync",
);

if (process.exitCode) console.error("lora sync dirty gate failed");
else console.log("ok");
