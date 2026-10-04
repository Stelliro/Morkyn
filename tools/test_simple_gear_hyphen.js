/**
 * Starting-gear string round-trip.
 *
 * The cards are the source of truth; the hidden starter_equipment string is
 * derived from them (names only, comma-separated). The legacy parser only runs
 * for an imported preset that has no starter_gear list.
 *
 * Guards:
 *  - A hyphen inside a name ("travel-stained coat", "3-day rations") is part of
 *    the name, not an effect break.
 *  - A plain comma list ("cloak, pouch, vial, tool, bread") is FIVE cards, not
 *    one card holding all five names (the original "everything in one Item box"
 *    bug).
 *  - Slots come from a bracketed slot word or from the item name, and the first
 *    item in each of FEET / TORSO / LEGS is marked required.
 *  - The derived string from cards parses back to the same names.
 *
 * Exit 0 on success.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");

function extractFunction(name) {
  const needle = `function ${name}(`;
  const start = src.indexOf(needle);
  if (start < 0) throw new Error(`missing ${name}`);
  const open = src.indexOf("{", start);
  let depth = 0;
  for (let j = open; j < src.length; j += 1) {
    const c = src[j];
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(start, j + 1);
    }
  }
  throw new Error(`unclosed ${name}`);
}

function extractConst(name) {
  const needle = `const ${name} =`;
  const start = src.indexOf(needle);
  if (start < 0) throw new Error(`missing const ${name}`);
  const end = src.indexOf(";\n", start);
  return src.slice(start, end + 1);
}

const code = [
  extractConst("GEAR_SLOT_OPTIONS"),
  extractConst("GEAR_SLOT_CODES"),
  extractConst("GEAR_REQUIRED_SLOTS"),
  extractConst("GEAR_SLOT_NAME_WORDS"),
  extractConst("GEAR_SLOT_WORD_ALIASES"),
  extractFunction("gearSlotFromWord"),
  extractFunction("gearSlotFromName"),
  extractFunction("gearItemsToStarterEquipment"),
  extractFunction("parseStarterEquipmentToGear"),
].join("\n");
const { gearItemsToStarterEquipment, parseStarterEquipmentToGear } = new Function(
  `${code}\nreturn { gearItemsToStarterEquipment, parseStarterEquipmentToGear };`,
)();

function assert(cond, message) {
  if (!cond) {
    console.error("FAIL:", message);
    process.exitCode = 1;
  }
}

// Hyphens stay inside names.
const hyphenated = parseStarterEquipmentToGear("travel-stained coat; 3-day rations");
assert(hyphenated.length === 2, `expected 2 cards, got ${hyphenated.length}`);
assert(hyphenated[0].name === "travel-stained coat", `name ${hyphenated[0].name}`);
assert(hyphenated[1].name === "3-day rations", `name ${hyphenated[1].name}`);
assert(!hyphenated[0].description && !hyphenated[1].description, JSON.stringify(hyphenated));

// The original bug: a comma list is one card per item.
const dump = parseStarterEquipmentToGear("travel-worn cloak, empty leather pouch, small glass vial, iron farming tool, rough loaf of bread");
assert(dump.length === 5, `comma list gave ${dump.length} card(s): ${JSON.stringify(dump)}`);
assert(dump[0].slot === "BACK", `cloak slot ${dump[0].slot}`);
assert(dump[3].slot === "MAIN", `tool slot ${dump[3].slot}`);
assert(dump[4].slot === "", `bread slot ${dump[4].slot}`);

// Slot words and names pick body slots; first of each basic is required.
const basics = parseStarterEquipmentToGear("dusty boots, patched tunic, rough breeches, spare boots");
assert(basics.map((i) => i.slot).join() === "FEET,TORSO,LEGS,FEET", basics.map((i) => i.slot).join());
assert(basics.slice(0, 3).every((i) => i.required), "first boots/tunic/breeches should be required");
assert(!basics[3].required, "second boots must not be required");

// Bracketed slot word and an em-dash description still work.
const detailed = parseStarterEquipmentToGear("lantern (belt) — lights 10 feet");
assert(detailed.length === 1, "lantern card missing");
assert(detailed[0].name === "lantern", `lantern name ${detailed[0].name}`);
assert(detailed[0].slot === "WAIST", `lantern slot ${detailed[0].slot}`);
assert(detailed[0].description === "lights 10 feet", `lantern description ${detailed[0].description}`);

// A comma inside brackets does not split the item.
const bracketed = parseStarterEquipmentToGear("coat (torso, outer), rope");
assert(bracketed.length === 2 && bracketed[0].name === "coat", JSON.stringify(bracketed));

// Cards -> derived string -> cards keeps every name.
const cards = [
  { name: "travel-stained coat", slot: "TORSO" },
  { name: "3-day rations", slot: "" },
  { name: "lantern", slot: "OFF", description: "lights 10 feet" },
];
const derived = gearItemsToStarterEquipment(cards);
assert(derived === "travel-stained coat, 3-day rations, lantern", derived);
const again = parseStarterEquipmentToGear(derived).map((i) => i.name);
assert(again.join("|") === "travel-stained coat|3-day rations|lantern", again.join("|"));

if (process.exitCode) {
  console.error("starting gear string round-trip failed");
} else {
  console.log("ok");
}
