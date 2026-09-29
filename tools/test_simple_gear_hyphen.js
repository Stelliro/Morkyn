/**
 * Simple gear round-trip must not treat hyphens inside names as effect breaks.
 *
 * parseStarterEquipmentToGear split on /—|–|-/ so "travel-stained coat" and
 * "3-day rations" gained effect text and effect_type "mixed". pullFormToSimple
 * builds cards from that parse; the next pushSimpleToForm writes them back as
 * "travel-stained coat [mixed] — stained coat".
 *
 * Exit 0 when hyphenated names stay look-only and emdash effects still round-trip.
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

const code =
  extractFunction("gearItemsToStarterEquipment") +
  "\n" +
  extractFunction("parseStarterEquipmentToGear");
const { gearItemsToStarterEquipment, parseStarterEquipmentToGear } = new Function(
  `${code}\nreturn { gearItemsToStarterEquipment, parseStarterEquipmentToGear };`,
)();

function assert(cond, message) {
  if (!cond) {
    console.error("FAIL:", message);
    process.exitCode = 1;
  }
}

const hyphenated = parseStarterEquipmentToGear("travel-stained coat; 3-day rations");
assert(hyphenated.length === 2, `expected 2 cards, got ${hyphenated.length}`);
for (const card of hyphenated) {
  assert(card.effect_type === "look_only", `${card.name} typed ${card.effect_type} effect=${card.effect}`);
  assert(!card.effect, `${card.name} stole effect ${card.effect}`);
}
assert(hyphenated[0].name === "travel-stained coat", `name ${hyphenated[0].name}`);
assert(hyphenated[1].name === "3-day rations", `name ${hyphenated[1].name}`);

const rewritten = gearItemsToStarterEquipment(hyphenated);
assert(!/\[mixed\]/i.test(rewritten), `round-trip stamped mixed: ${rewritten}`);
assert(rewritten.includes("travel-stained coat"), rewritten);
assert(rewritten.includes("3-day rations"), rewritten);

const detailed = parseStarterEquipmentToGear("lantern (belt) — lights 10 feet");
assert(detailed.length === 1, "lantern card missing");
assert(detailed[0].name === "lantern", `lantern name ${detailed[0].name}`);
assert(detailed[0].slot === "belt", `lantern slot ${detailed[0].slot}`);
assert(detailed[0].effect === "lights 10 feet", `lantern effect ${detailed[0].effect}`);
assert(detailed[0].effect_type === "mixed", "explicit emdash effect should still count as mixed when untagged");

const spaced = parseStarterEquipmentToGear("hooded cloak - sheds rain");
assert(spaced[0].name === "hooded cloak", `spaced name ${spaced[0].name}`);
assert(spaced[0].effect === "sheds rain", `spaced effect ${spaced[0].effect}`);

const kept = gearItemsToStarterEquipment([
  { name: "travel-stained coat", slot: "torso", effect_type: "look_only", effect: "" },
  { name: "lantern", slot: "belt", effect_type: "mixed", effect: "lights 10 feet" },
]);
const again = parseStarterEquipmentToGear(kept);
assert(again[0].name === "travel-stained coat" && again[0].effect_type === "look_only", JSON.stringify(again[0]));
assert(again[0].slot === "torso", JSON.stringify(again[0]));
assert(again[1].name === "lantern" && again[1].effect === "lights 10 feet", JSON.stringify(again[1]));
assert(again[1].effect_type === "mixed" && again[1].slot === "belt", JSON.stringify(again[1]));

if (process.exitCode) {
  console.error("simple gear hyphen round-trip failed");
} else {
  console.log("ok");
}
