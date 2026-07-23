const setupView = document.querySelector("#setupView");
const gameView = document.querySelector("#gameView");
const mainMenuView = document.querySelector("#mainMenuView");
const setupForm = document.querySelector("#setupForm");
const setupSections = Array.from(document.querySelectorAll(".setupSection"));
const setupStepButtons = Array.from(document.querySelectorAll("[data-setup-step]"));
const setupPrevButton = document.querySelector("#setupPrev");
const setupNextButton = document.querySelector("#setupNext");
const setupStepStatus = document.querySelector("#setupStepStatus");
const setupModelButton = document.querySelector("#setupModelButton");

const updatesButton = document.querySelector("#updatesButton");
const setupStartButton = document.querySelector("#setupStart");
const setupStartMobileButton = document.querySelector("#setupStartMobile");
const setupMoreToggle = document.querySelector("#setupMoreToggle");
const setupActionsMore = document.querySelector("#setupActionsMore");
const saveSetupSettingsButton = document.querySelector("#saveSetupSettings");
const setupSettingsFile = document.querySelector("#setupSettingsFile");
const randomizeSetup = document.querySelector("#randomizeSetup");
const legalModal = document.querySelector("#legalModal");
const legalModalTitle = document.querySelector("#legalModalTitle");
const legalModalSubtitle = document.querySelector("#legalModalSubtitle");
const legalModalContent = document.querySelector("#legalModalContent");
const closeLegalModal = document.querySelector("#closeLegalModal");
const turnForm = document.querySelector("#turnForm");
const turnInput = document.querySelector("#turnInput");
const sendButton = document.querySelector("#sendButton");
const continueButton = document.querySelector("#continueButton");
const suggestButton = document.querySelector("#suggestButton");
const suggestionPanel = document.querySelector("#suggestionPanel");
const suggestionsEl = document.querySelector("#suggestionList");
const suggestionInstruction = document.querySelector("#suggestionInstruction");
const regenSuggestionsButton = document.querySelector("#regenSuggestionsButton");
const refreshButton = document.querySelector("#refreshButton");
const newGameButton = document.querySelector("#newGameButton");
const regenerateButton = document.querySelector("#regenerateButton");
const rewindButton = document.querySelector("#rewindButton");
const exportButton = document.querySelector("#exportButton");
const importButton = document.querySelector("#importButton");
const saveSlotButton = document.querySelector("#saveSlotButton");
const loadSlotButton = document.querySelector("#loadSlotButton");
const compactModeButton = document.querySelector("#compactModeButton");
const modelButton = document.querySelector("#modelButton");
const importFile = document.querySelector("#importFile");
const COMPACT_STORAGE_KEY = "ai_rpg_compact_mode";
const locationLine = document.querySelector("#locationLine");
const latestInput = document.querySelector("#latestInput");
const latestOutput = document.querySelector("#latestOutput");
const historyEl = document.querySelector("#history");
const indexTabs = document.querySelector("#indexTabs");
const indexContent = document.querySelector("#indexContent");
const abilityOptions = document.querySelector("#abilityOptions");
const abilityList = document.querySelector("#abilityList");
const addAbilityButton = document.querySelector("#addAbilityButton");
const randomAbilityButton = document.querySelector("#randomAbilityButton");
const lockAbilityCount = document.querySelector("#lockAbilityCount");
const systemOptions = document.querySelector("#systemOptions");
const formerLifeIdentity = document.querySelector("#formerLifeIdentity");
const entityMenu = document.querySelector("#entityMenu");
const closeEntityMenu = document.querySelector("#closeEntityMenu");
const entityTitle = document.querySelector("#entityTitle");
const entityMeta = document.querySelector("#entityMeta");
const entityBody = document.querySelector("#entityBody");
const insertEntityRef = document.querySelector("#insertEntityRef");
const aliasForm = document.querySelector("#aliasForm");
const aliasInput = document.querySelector("#aliasInput");
const modelModal = document.querySelector("#modelModal");
const modelModalToggle = document.querySelector("#modelModalToggle");
const closeModelModal = document.querySelector("#closeModelModal");
const modelModalContent = document.querySelector("#modelModalContent");
const startSplash = document.querySelector("#startSplash");
const startSplashLog = document.querySelector("#startSplashLog");
const startSplashHeartbeat = document.querySelector("#startSplashHeartbeat");
const startSplashHeartbeatTitle = document.querySelector("#startSplashHeartbeatTitle");
const startSplashHeartbeatText = document.querySelector("#startSplashHeartbeatText");
const startSplashPhase = document.querySelector("#startSplashPhase");
const startSplashDraft = document.querySelector("#startSplashDraft");

let state = null;
let activeTab = "player";
let selectedEntity = null;
let bible = null;
let searchResults = null;
let setupStep = 0;
let modelConfig = null;
let aiBusy = false;
let aiQueue = Promise.resolve();
let setupRandomizeLockDepth = 0;
let startSplashTimers = [];
let startSplashHeartbeatTimer = null;
let generationProgressTimer = null;
let generationProgressSeenLines = 0;
let generationProgressLastPreview = "";
let turnWaitTimer = null;
let turnStreamTimer = null;
let historyPage = 0;

const DEFAULT_GGUF_MODEL = "";
const SETUP_SETTINGS_FORMAT = "ai-rpg-setup-settings-v1";
const HISTORY_PAGE_SIZE = 6;
const HISTORY_OPEN_STATE_KEY = "ai-rpg-history-open-v1";
const START_SPLASH_REASSURANCE = [
  "Waiting for the first model response; the request is still open.",
  "Large GGUF models can spend a while loading before text appears.",
  "The backend is still holding the start request; this page has not frozen.",
  "The model may be drafting the opening scene or warming GPU memory.",
  "If the verifier is running, it may be checking references and state changes.",
  "Long local generations are normal; keep this tab open while it finishes.",
];
const TURN_WAIT_REASSURANCE = {
  turn: [
    "The turn request is still open; the model has not stopped.",
    "Local models can pause before the first token, especially after a big context packet.",
    "The draft or verifier may still be checking references and state changes.",
    "Keep this tab open while the RPG finishes the response.",
  ],
  continue: [
    "The scene is still advancing; the model has not stopped.",
    "A continue turn may still draft, verify, and update world state.",
    "Long local waits usually mean model load, context reading, or verification.",
    "The app is still waiting on the server response.",
  ],
  regenerate: [
    "Regeneration is still running from the saved snapshot.",
    "The model may be rewriting the draft before the verifier checks it.",
    "World state is being restored and replayed for this response.",
    "Keep this tab open; the request is still alive.",
  ],
};

const PREFIX = {
  npc: "@",
  location: "#",
  item: "!",
  event: "&",
};

const OPTIONAL_IDENTITY_FIELDS = new Set(["player_public_name", "player_title"]);
const OPTIONAL_IDENTITY_FILL_CHANCE = {
  player_public_name: 0.22,
  player_title: 0.14,
};
const ABILITY_ORIGINS = new Set(["none", "acquired", "innate"]);

const RANDOM_SETUP = {
  player_name: ["Wanderer", "Mara", "Corvin", "Iris Vale", "Ren", "Sable", "Tamsin", "Kael"],
  player_public_name: ["", "Ash", "River", "Patch", "Northlight", "Second Bell", "Vellum"],
  player_title: ["", "the Weatherwise", "of Kiln Street", "the Long Listener", "Under New Moons", "the Spare Key"],
  player_age: ["17", "19", "24", "31", "middle-aged", "appears 30", "adult"],
  // Weighted: male/female majority; rare exotic (client offline fallback).
  player_sex: [
    "female", "female", "female", "female", "female", "female", "female", "female", "female",
    "male", "male", "male", "male", "male", "male", "male", "male", "male",
    "", "",
    "intersex",
    "sexless or constructed",
    "varies by form",
  ],
  previous_life_age: ["19", "27", "34", "46", "elderly", "unknown"],
  previous_life_sex: [
    "female", "female", "female", "female", "female", "female", "female", "female", "female",
    "male", "male", "male", "male", "male", "male", "male", "male", "male",
    "", "",
    "intersex",
    "sexless or constructed",
    "varies by form",
  ],
  special_ability_origin: ["none", "acquired", "innate"],
  backstory_mode: ["known", "hidden", "fragmented memories", "reincarnated", "transmigrated", "nameless drifter"],
  memory_policy: ["known", "ordinary memory", "details emerge through choices", "rumors may be wrong", "private details stay private", "remembers former life", "former life fragments"],
  character_backstory: [
    "Born in a canal district where freight crews raised children as extra hands, they grew up reading cargo marks, weather signs, and people's excuses. Before the story begins, they worked as a route clerk who kept small settlements supplied, and they reached the starting area carrying one delayed delivery, two unpaid favors, and a fear that their last ledger was deliberately altered.",
    "Born in a hill village that treated old ruins as common landmarks, they spent most of their life repairing tools, copying maps, and guiding travelers through roads locals considered ordinary. They left after a winter landslide exposed sealed stonework under the village shrine, bringing practical skills, a few local contacts, and one question their elders refused to answer.",
    "In their former life, they died in a hospital stairwell during a citywide blackout after spending years as an overworked emergency technician. They woke in this world with most memories intact but no proof of who they had been, carrying modern habits of triage, suspicion of official silence, and a need to learn which rules of the new world can still kill them.",
    "Born on the edge of a company town, they were trained young to weigh ore, settle shift disputes, and keep peace between hungry workers and richer overseers. They arrived at the starting point after their home contract collapsed, with a known name among laborers, a practical distrust of nobles, and a short list of people who may blame them for surviving.",
    "They remember being born somewhere else entirely: a quiet apartment, a locked office job, and a fatal accident on a rain-slick road. This new body has its own calluses and local debts, so the player begins with two lives worth of instincts but only fragments of why this world's people already seem to expect something from them.",
  ],
  hair: ["short brown hair", "long silver braid", "messy black hair", "cropped sandy hair", "wavy auburn hair"],
  facial_features: [
    "green eyes, light freckles, soft jaw",
    "dark brown eyes, thin scar on left cheek",
    "grey eyes, tired lids, square jaw",
    "hazel eyes, faint laugh lines, straight nose",
  ],
  appearance: [
    "torso: travel-stained coat; feet: dusty boots; waist: rope coil",
    "torso: plain work tunic; torso: leather apron; hands: work gloves; feet: practical boots",
    "torso: frayed cloak; legs: patched trousers; bag: worn satchel",
    "torso: simple street clothes; feet: cheap shoes; bag: thin travel bag",
  ],
  starter_equipment: [
    "worn coat, coiled rope, pocket knife, dusty boots, water skin, 3 days rations",
    "plain clothes, work gloves, small tool pouch, practical boots, copper coins",
    "travel cloak, empty satchel, wooden charm, heel of bread",
    "secondhand jacket, notebook stub, stub of chalk, water flask",
  ],
  skill_style: ["standard", "generous", "training-heavy", "strict"],
  proficiency_access: ["learned", "familiar actions free", "only expert tasks require training"],
  new_skill_frequency: ["normal", "very rare", "rare", "frequent", "very frequent"],
  world_style: [
    "frontier dark fantasy",
    "wuxia sect politics",
    "system apocalypse",
    "post-collapse settlement",
    "mage academy intrigue",
    "low magic mercantile city",
    "space frontier salvage",
  ],
  start_location: [
    "Mosswake Gate",
    "Blackwater Relay",
    "The Ninth Stair",
    "Cinder Market",
    "Ashford Clinic",
    "Red Lantern Dock",
    "Saint Vale Station",
  ],
  tone: ["grounded adventure", "survival pressure", "political intrigue", "mythic progression", "grim road story"],
  economy: ["scarce", "barter-heavy", "coin-driven", "guild-controlled"],
  loot_rarity: ["earned and uncommon", "scarce mundane", "generous adventuring", "high-magic loot"],
  inventory_weight_limit: [45, 60, 80, 120],
  inventory_slot_limit: [18, 24, 32, 40],
  inventory_rules: [
    "Backpacks add organization more than strength; magic storage is rare and carries risks.",
    "Accessory slots follow anatomy unless an ability, spell, or special item creates more room.",
    "Superhuman stacks require clear stats, magic, or container support.",
  ],
  magic_level: ["rare", "forbidden", "common utility", "cultivation", "none"],
  world_races: ["human", "elf", "dwarf", "beastfolk"],
  race_magic_rarity: ["same as world magic", "rare except gifted races", "common for specific races", "bloodline locked", "cultural training based"],
  race_magic_rules: [
    "Humans need formal training, elves inherit low magic, dwarves specialize in rune craft, and beastfolk rarely cast spells but sense spirits.",
    "Magic is learned culturally: each people has different schools, taboos, and costs rather than equal access.",
    "Only a few bloodlines can cast, but every race has at least one rare path into magic through training, vows, or relics.",
  ],
  race_ability_rules: [
    "Humans have broad training access, elves can sense old growth and glamour, dwarves learn craft-oaths, beastfolk inherit heightened senses.",
    "Racial abilities are social and biological rather than class powers; they should help in scenes without replacing skills.",
    "Innate gifts are modest at the start and stronger racial arts require culture, mentors, rites, or long practice.",
  ],
  custom_skills: [
    "Do not seed starting skills; discover skill names only after repeated use, training, or clear milestones.",
    "Specialized proficiencies require mentors or manuals; ordinary attempts are allowed, but mastery needs downtime.",
    "Combat, social, craft, and survival skills appear only after the player actually practices or earns them in play.",
  ],
  tech_level: ["iron age", "medieval", "early industrial", "near future", "spacefaring salvage"],
  custom_style: [
    "",
    "Keep the opening local and personal before revealing larger threats.",
    "Every settlement should have at least one practical reason to exist.",
    "Avoid chosen-one framing; make reputation earned through visible choices.",
  ],
  npc_density: ["moderate", "sparse", "dense", "faction-heavy"],
  quest_style: ["emergent", "job board", "faction chains", "personal mysteries"],
  faction_pressure: ["local disputes", "sect hierarchy", "guild control", "military occupation", "hidden cults"],
  npc_stat_scaling: ["relative ranks", "mostly weaker", "near player", "swingy ranks", "elite-heavy"],
  npc_skill_frequency: ["some trained NPCs", "no special NPC skills", "rare specialists", "many trained NPCs", "almost everyone has skills"],
  rank_scale: ["F,E,D,C,B,A,S,SS,SSS", "D,C,B,A,S", "Common,Trained,Veteran,Elite,Mythic"],
  difficulty: ["normal", "easy", "hard", "brutal"],
  narration_detail: ["balanced", "rich", "expansive", "concise"],
  skill_growth_speed: ["normal", "very slow", "slow", "fast", "very fast"],
  proficiency_growth_speed: ["normal", "very slow", "slow", "fast", "very fast"],
  xp_growth_speed: ["normal", "very slow", "slow", "fast", "very fast"],
  death_rules: ["downed, not deleted", "lasting injuries", "permadeath threat", "narrative setback"],
  system_style: ["subtle blue-window system", "cold quest-log interface", "cultivation status pane", "diegetic omen prompts"],
};

const GROWTH_MATH_SAMPLES = [
  "rank F→E@80 E→D@200 D→C@450 C→B@900; domain use 5-12 skill XP × risk (1 safe/2 contested/3 life-risk); XP_to_next = 50 * rank_index^1.4; after C practice XP ×0.5 until mentor breakthrough; +1 domain check per rank above F",
  "levels 1-10; XP_to_next = 30 + 12*level; successful use grants 3-8 XP; crit success ×2; soft cap at L6 (XP ×0.6 until setback recovery); effect magnitude +8% per level",
  "thresholds F0 E100 D250 C500 B1000 A2000 S4000; practice 4 XP, contested 10, mentor drill 15; rank bonus +1 check / +5% effect; breakthrough needed after B",
];

const ABILITY_PRESETS = [
  {
    name: "Echo Step",
    description: "A short burst of impossible movement, useful for escapes or sudden positioning.",
    locked: false,
    prerequisites: "",
    cost: "",
    growth_math: GROWTH_MATH_SAMPLES[0],
  },
  {
    name: "Ashen Oath",
    description: "Can sense when someone nearby is hiding a binding promise or unpaid debt.",
    locked: true,
    prerequisites: "Awakens after witnessing a broken oath with real consequences.",
    cost: "",
    growth_math: GROWTH_MATH_SAMPLES[1],
  },
  {
    name: "Thread Sense",
    description: "Briefly notices the emotional weight attached to an object or place.",
    locked: false,
    prerequisites: "",
    cost: "Brief fatigue or sensory overload after repeated use.",
    growth_math: GROWTH_MATH_SAMPLES[2],
  },
  {
    name: "Last Light",
    description: "Survives one fatal mistake as a lasting injury instead of immediate death.",
    locked: true,
    prerequisites: "Only unlocks after the player accepts a serious personal risk.",
    cost: "One permanent scar, debt, or consequence chosen by context.",
    growth_math: "single-use breakthrough ability; no rank ladder until unlocked; after unlock, recovery XP only via narrative milestones (DM awards 1 breakthrough charge per major life risk survived, max 1 held)",
  },
  {
    name: "Quiet Ledger",
    description: "Instinctively tracks small favors and who last broke a minor deal nearby.",
    locked: false,
    prerequisites: "",
    cost: "Distraction in crowded social noise.",
    growth_math: GROWTH_MATH_SAMPLES[0],
  },
  {
    name: "Rust Touch",
    description: "Slightly accelerates wear on one tool or lock with prolonged contact—barely useful at first.",
    locked: true,
    prerequisites: "Needs a full night handling scrap metal without rest.",
    cost: "Numb fingers for hours.",
    growth_math: GROWTH_MATH_SAMPLES[1],
  },
  {
    name: "Ink Memory",
    description: "Perfectly recalls one short written passage seen in the last day, nothing more.",
    locked: false,
    prerequisites: "",
    cost: "Mild headache if forced twice in a row.",
    growth_math: GROWTH_MATH_SAMPLES[2],
  },
  {
    name: "Second Breath",
    description: "Once per hard day, recovers a single exhausted breath mid-sprint or climb.",
    locked: false,
    prerequisites: "",
    cost: "Deep hunger afterward.",
    growth_math: GROWTH_MATH_SAMPLES[0],
  },
];

const SYSTEM_STYLE_DESCRIPTIONS = {
  "subtle blue-window system": "A familiar status window appears briefly for stats, prompts, and simple notifications. NPC awareness depends on the world rules.",
  "cold quest-log interface": "The system feels transactional: tasks, rewards, warnings, and failures appear like a detached quest ledger.",
  "cultivation status pane": "Progress appears as realms, breakthroughs, affinities, bottlenecks, and inner-state feedback.",
  "diegetic omen prompts": "The world itself signals information through omens, dreams, symbols, coincidences, or supernatural intuition.",
  custom: "Write exactly how the system interface should appear and what it is allowed to reveal.",
};

const RANDOM_GROUPS = {
  character: ["backstory_mode", "memory_policy", "character_backstory", "hair", "facial_features", "appearance", "starter_equipment", "player_name", "player_public_name", "player_title", "player_age", "player_sex", "previous_life_age", "previous_life_sex", "special_ability_origin", "special_abilities"],
  // Powers step: ability cards + custom skill rules (compounding / XP / tracking live here)
  powers: ["special_ability_origin", "special_abilities", "custom_skills"],
  world: ["world_style", "magic_level", "world_races", "race_magic_enabled", "race_magic_rarity", "tech_level", "tone", "economy", "start_location", "custom_style", "race_magic_rules", "race_ability_rules"],
  people: ["npc_density", "quest_style", "faction_pressure", "npc_stat_scaling", "npc_skill_frequency", "rank_scale"],
  rules: ["difficulty", "death_rules", "narration_detail", "loot_rarity", "inventory_weight_limit", "inventory_slot_limit", "inventory_rules", "leveling_system", "game_system", "proficiency_system", "skill_levels_enabled", "skill_style", "proficiency_access", "new_skill_frequency", "xp_growth_speed", "skill_growth_speed", "proficiency_growth_speed", "system_style", "custom_skills"],
  checks: ["dice_checks_enabled", "dice_sides", "check_difficulty", "event_check_frequency", "encounter_check_frequency", "partial_on_specialized_skill", "negative_outcomes", "show_rolls_in_ui", "attribute_floor_for_partial", "specialized_skill_partial_threshold", "custom_check_notes"],
};

const RANDOM_GROUP_ORDER = ["character", "world", "people", "rules", "checks"];
// Dependency-safe composer load order (mirrors app/setup_composer.py).
// Refreshed from GET /api/setup/composer when available.
let RANDOM_FIELD_ORDER = [
  "world_style",
  "tone",
  "tech_level",
  "magic_level",
  "economy",
  "custom_style",
  "world_races",
  "race_magic_enabled",
  "race_magic_rarity",
  "race_magic_rules",
  "race_ability_rules",
  "difficulty",
  "death_rules",
  "narration_detail",
  "loot_rarity",
  "inventory_weight_limit",
  "inventory_slot_limit",
  "inventory_rules",
  "leveling_system",
  "xp_growth_speed",
  "game_system",
  "system_style",
  "proficiency_system",
  "skill_levels_enabled",
  "skill_style",
  "proficiency_access",
  "new_skill_frequency",
  "skill_growth_speed",
  "proficiency_growth_speed",
  "custom_skills",
  "npc_density",
  "quest_style",
  "faction_pressure",
  "npc_stat_scaling",
  "npc_skill_frequency",
  "rank_scale",
  "backstory_mode",
  "memory_policy",
  "character_backstory",
  "hair",
  "facial_features",
  "appearance",
  "starter_equipment",
  "player_name",
  "player_public_name",
  "player_title",
  "player_age",
  "player_sex",
  "previous_life_age",
  "previous_life_sex",
  "start_location",
  "special_ability_origin",
  "special_abilities",
];

/** Last compiled Randomize intent → passed into field rolls and Start playthrough. */
let lastComposeIntent = null;
let lastSessionTheme = null;

/**
 * One-click director seeds for Randomize.
 * Labels stay short and plain; `idea` steers compose + field rolls (max ~400 chars).
 */
const DIRECTOR_PRESETS = [
  {
    id: "one_skill",
    label: "One Skill",
    idea:
      "Hardcore single-skill isekai: ordinary person with exactly one weak compounding skill/ability (domain varies—not weather/observation by default). Put calculable growth math on the ability Growth Math box (XP curves, rank thresholds, risk mult, soft caps, rank→bonus). Custom skills hold seed/tracking/limits fiction. Soft caps, no second combat toolkit. Local stakes, subtle UI, fair DM.",
  },
  {
    id: "fantasy",
    label: "Fantasy",
    idea:
      "Classic fantasy RPG: kingdoms, roads, ruins, and workable magic. Balanced difficulty; adventure and discovery; clear rules without loud game-UI; neither grimdark nor pure cozy. Local quests that can scale.",
  },
  {
    id: "cyberpunk",
    label: "Cyberpunk",
    idea:
      "Near-future cyberpunk RPG: megacorps, street work, chrome, and debt. Hard-normal difficulty; tech and social leverage over magic; noir tone; jobs stay local until they touch bigger systems.",
  },
  {
    id: "adventurers",
    label: "Adventurers",
    idea:
      "Tabletop-campaign fantasy in the spirit of classic D&D: dungeons, wilderness, factions, and party roles in the world. Fair challenge, loot and levels matter, quest hooks without video-game menus.",
  },
  {
    id: "iron_front",
    label: "Iron Front",
    idea:
      "War-scarred grim setting in a Warhammer vein: faith, heresy, brutal infantry, scarce trust. Hard difficulty; horror and attrition; loyalty and survival over glory; no power fantasy.",
  },
  {
    id: "court",
    label: "Court",
    idea:
      "Political intrigue RPG: salons, succession, blackmail, soft power. Low open combat; reputation and leverage drive play; normal difficulty; every public move has consequences.",
  },
  {
    id: "frontier",
    label: "Frontier",
    idea:
      "Remote frontier RPG: thin law, weather, supply, and small settlements. Survival and craft first; modest magic if any; hard-normal difficulty; community stakes over empire plots.",
  },
  {
    id: "depth",
    label: "Depths",
    idea:
      "Underworld and dungeon-depth RPG: delves, rival crews, ancient pressure. Resource and light management; hard-normal difficulty; discoveries cost blood; surface politics stay distant until they don't.",
  },
];

const SETTING_INFO = {
  player_name: {
    description: "The name shown in player records and story summaries.",
  },
  player_public_name: {
    description: "A rare public name, alias, or nickname. Usually blank unless the backstory or Backstory Mode gives NPCs a reason to know another name.",
    customPlaceholder: "Example: the Red Courier",
  },
  player_title: {
    description: "A rare epithet or formal title. Usually blank unless the backstory implies reputation, former power, reincarnation status, office, or rumors.",
    customPlaceholder: "Example: the one who opened the Black Gate",
  },
  player_age: {
    description: "The character's current age or apparent age in this life. Text is allowed for unusual species, constructs, or immortal starts.",
  },
  player_sex: {
    description: "Current biological sex or body category. Randomize usually picks female or male for ordinary people; sexless/constructed and varies-by-form stay rare unless the world supports them. Leave blank when irrelevant.",
    customPlaceholder: "Example: changes with moon phase, not applicable, unknown to player",
  },
  previous_life_age: {
    description: "For reincarnated or transmigrated starts, the age the character remembers from the former life.",
  },
  previous_life_sex: {
    description: "Former-life sex for reincarnated/transmigrated starts. Prefer male/female for ordinary former lives; exotic categories only when that body was clearly nonstandard.",
    customPlaceholder: "Example: different from current body, unknown, not applicable",
  },
  special_ability_origin: {
    description: "Controls whether setup defines no special abilities, abilities acquired through play, or innate abilities the character starts with.",
  },
  backstory_mode: {
    description: "Controls how much of the character's past is known at the start and how carefully the model should reveal it.",
    customPlaceholder: "Example: reincarnated with memories intact, but the new body's local past is unclear",
  },
  memory_policy: {
    description: "Controls whether memories are stable, slowly recovered, triggered by events, known by NPCs, or may stay lost.",
    customPlaceholder: "Example: memories only return when an old witness recognizes the title",
  },
  character_backstory: {
    description: "Concrete origin details: where the character came from, how they lived before play, why they reached the opening, and death/reincarnation facts if relevant.",
    customPlaceholder: "Example: born in a river town, worked as a debt courier, died in another world during a blackout, then woke here with only practical memories intact",
  },
  hair: {
    description: "Hair for art: length, color, and style. Separate from face details and clothing.",
    customPlaceholder: "Example: short brown hair",
  },
  facial_features: {
    description: "Face-only portrait cues: eyes, freckles, scars, jaw. Not hair or clothes.",
    customPlaceholder: "Example: green eyes, light freckles, soft jaw",
  },
  appearance: {
    description:
      "Clothing worn at Start (fact-checked with starter gear) and used for art. Prefer zone:item. Isekai arrival ≠ plate armor; put hair/face in their fields.",
    customPlaceholder: "Example: torso: travel clothes; feet: practical shoes",
  },
  starter_equipment: {
    description:
      "Items already owned when you press Start (fact-checked). Isekai/summon = clothes/pockets from arrival only — no free shield/sword. Reincarnated = this-life gear. Native = must fit the backstory job. God/system gifts happen after Start.",
    customPlaceholder: "Example: worn coat, pocket notebook, copper coins, water flask",
  },
  skill_style: {
    description: "Controls how hard it is to gain useful skills. This is about progression pressure, not character class.",
    customPlaceholder: "Example: skills improve only after tutoring, repeated practice, and real risk",
  },
  skill_levels_enabled: {
    description: "When on, individual skills can level up over time. When off, skills behave more like unlocked proficiencies.",
  },
  new_skill_frequency: {
    description: "Controls how often the player can discover or gain entirely new skills.",
    customPlaceholder: "Example: new skills require mentors, books, or major breakthroughs",
  },
  proficiency_system: {
    description: "When on, specialized actions may require learned proficiencies. When off, ordinary actions are available immediately.",
  },
  proficiency_access: {
    description: "Controls what the player must learn before reliably using specialized proficiencies.",
    customPlaceholder: "Example: basic attempts are allowed, mastery requires a mentor or manual",
  },
  custom_skills: {
    description:
      "Comma-separated custom proficiencies and training-rule phrases (seed skill name, tracking style, hard limits). Put calculable XP/rank formulas on each ability's Growth Math box when the power compounds.",
  },
  world_style: {
    description: "The main genre and setting shape. This strongly affects locations, NPC roles, items, and threats.",
    customPlaceholder: "Example: dieselpunk desert kingdoms with haunted radio towers",
  },
  start_location: {
    description: "The first indexed location where play begins.",
  },
  tone: {
    description: "Controls how harsh, heroic, political, or grounded the narration should feel.",
    customPlaceholder: "Example: tense but hopeful, with danger coming from scarcity and secrets",
  },
  economy: {
    description: "Controls how money, trade, scarcity, and rewards usually work.",
    customPlaceholder: "Example: reputation-based favors, no universal currency",
  },
  magic_level: {
    description: "Sets how common supernatural power is and how openly people talk about it.",
    customPlaceholder: "Example: miracles are real but only work through dangerous bargains",
  },
  world_races: {
    description: "Controls which peoples commonly exist in the world. This affects NPC generation and social assumptions.",
    customPlaceholder: "Example: humans, moon elves, ash dwarves, riverkin",
  },
  race_magic_enabled: {
    description: "When on, some races or ancestries may have different chances of using magic.",
  },
  race_magic_rarity: {
    description: "Controls how strongly race or ancestry changes magic access.",
    customPlaceholder: "Example: elves often know low magic, humans usually need training, dwarves favor runes",
  },
  race_magic_rules: {
    description: "Exact rules for each race's access to spellcasting, mana, cultivation, miracles, or other magical practice.",
  },
  race_ability_rules: {
    description: "Exact rules for each race's innate gifts, learned racial arts, restrictions, and non-magical special abilities.",
  },
  tech_level: {
    description: "Sets the tools, weapons, medicine, travel, and infrastructure people can plausibly use.",
    customPlaceholder: "Example: Renaissance cities with broken orbital relics",
  },
  custom_style: {
    description: "Optional extra world rules, themes, bans, or must-have ideas.",
  },
  npc_density: {
    description: "Controls how many named people the game should create and track in each area.",
    customPlaceholder: "Example: few NPCs, but each one has strong ties and secrets",
  },
  quest_style: {
    description: "Controls how opportunities appear: naturally, through boards, factions, or personal mysteries.",
    customPlaceholder: "Example: rumors from NPCs, no formal quests unless a faction offers one",
  },
  faction_pressure: {
    description: "Sets what kind of groups hold power and how much they interfere with daily life.",
    customPlaceholder: "Example: merchant families, railway unions, and a quiet religious court",
  },
  npc_stat_scaling: {
    description: "Controls how NPC and enemy stats are ranked relative to the player when first observed.",
    customPlaceholder: "Example: civilians weaker, guards near player, named rivals often one rank higher",
  },
  npc_skill_frequency: {
    description: "Controls how often NPCs and enemies have notable ranked skills instead of ordinary competence.",
    customPlaceholder: "Example: only faction officers and monsters have ranked skills",
  },
  rank_scale: {
    description: "The labels used for relative NPC/enemy stats and skills. Default goes from F up to SSS.",
    customPlaceholder: "Example: Weak, Average, Trained, Elite, Legendary",
  },
  difficulty: {
    description: "Controls enemy scaling against the player. Easier settings make higher-ranked enemies uncommon; harder settings make them more likely.",
    customPlaceholder: "Example: enemies are usually near player rank, but bosses are two ranks higher",
  },
  death_rules: {
    description: "Defines what happens when the player loses badly.",
    customPlaceholder: "Example: death is possible only after repeated ignored warnings",
  },
  narration_detail: {
    description: "Controls how much prose the model should spend on scene texture, NPC reactions, consequences, and choice openings.",
    customPlaceholder: "Example: write 4 detailed scene beats unless the player asks for a quick check",
  },
  loot_rarity: {
    description: "Controls how often the DM introduces mundane, rare, enchanted, unique, and legendary items.",
    customPlaceholder: "Example: mundane supplies are common, enchanted gear requires named risks or faction access",
  },
  inventory_weight_limit: {
    description: "The base carry weight before backpacks, abilities, spells, or dimensional storage change it.",
  },
  inventory_slot_limit: {
    description: "The base packed inventory slots before backpacks, pouches, sheaths, or magical storage add more organization.",
  },
  inventory_rules: {
    description: "Optional carrying, equipment, storage magic, accessory slot, and superhuman quantity rules for this playthrough.",
    customPlaceholder: "Example: rings are limited by anatomy unless a spell creates extra finger slots; dimensional bags are rare and risky",
  },
  leveling_system: {
    description: "If enabled, the player gains levels and XP. If disabled, growth is handled through training, items, and story changes.",
  },
  xp_growth_speed: {
    description: "Controls how quickly XP is awarded when leveling is enabled.",
    customPlaceholder: "Example: XP only from major completed goals",
  },
  skill_growth_speed: {
    description: "Controls how quickly skills improve from use, pressure, training, or success.",
    customPlaceholder: "Example: combat improves slowly, social skills improve normally",
  },
  proficiency_growth_speed: {
    description: "Controls how quickly new proficiencies are learned or upgraded.",
    customPlaceholder: "Example: proficiencies require downtime and a teacher",
  },
  game_system: {
    description: "Adds an in-world interface like status windows, quests, achievements, or system prompts.",
  },
  system_style: {
    description: "Controls how the in-world system appears and how openly NPCs understand it.",
    customPlaceholder: "Example: only appears in dreams, speaks in legal contracts",
  },
};

const SETTING_LIMITS = {
  player_public_name: 100,
  player_title: 100,
  player_age: 60,
  player_sex: 80,
  previous_life_age: 60,
  previous_life_sex: 80,
  backstory_mode: 100,
  memory_policy: 120,
  character_backstory: 1600,
  hair: 120,
  facial_features: 300,
  appearance: 400,
  starter_equipment: 500,
  skill_style: 60,
  custom_skills: 1200,
  new_skill_frequency: 80,
  proficiency_access: 80,
  skill_growth_speed: 80,
  proficiency_growth_speed: 80,
  xp_growth_speed: 80,
  world_style: 120,
  tone: 100,
  economy: 80,
  magic_level: 80,
  world_races: 400,
  race_magic_rarity: 100,
  race_magic_rules: 1200,
  race_ability_rules: 1200,
  tech_level: 80,
  npc_density: 80,
  quest_style: 80,
  faction_pressure: 100,
  npc_stat_scaling: 80,
  npc_skill_frequency: 100,
  rank_scale: 100,
  difficulty: 60,
  death_rules: 80,
  narration_detail: 120,
  loot_rarity: 80,
  inventory_rules: 900,
  system_style: 120,
};

const ACTION_HELP_TARGETS = [
  ["#setupModelButton", "Open the local LLM connection settings used for setup randomization, AI text fill, suggestions, and gameplay turns."],
  ["#saveSetupSettings", "Download the current setup form, ability cards, locks, and custom rules as a reusable JSON settings file."],
  ["#loadSetupSettingsButton", "Load a previously saved setup settings JSON file back into the setup form."],
  ["#randomizeSetup", "Randomize the whole setup in dependency order. Locked fields are skipped. Optional idea box beside it steers the overall concept."],
  ["#randomizeSetupPrompt", "Optional. Describe the kind of run you want (tone, genre, hook). Full Randomize uses this as overall intent while still filling each field."],
  ["#directorPresets", "Director seeds: one-click genre templates (One Skill, Fantasy, Cyberpunk, Adventurers…). Fills the idea box and runs Randomize."],
  // Intent summary help is attached to the title in renderIntentSummary (not the whole bar).
  ["input[name='session_theme_model']", "Optional model for this playthrough only (Ollama tag, API model, or GGUF path). Wins over the adapter map. Save Model applies it; blank clears."],
  ["#setupStart", "Start the playthrough with the current setup and ask the LLM to write the opening scene before the player acts."],
  ["#setupPrev", "Move to the previous setup step without changing any filled values."],
  ["#setupNext", "Move to the next setup step. On the final step, this starts the playthrough."],
  ["#randomAbilityButton", "Randomize the Special Abilities list. If Lock Count is on, only ability contents change; the number of cards stays fixed."],
  ["#addAbilityButton", "Add a blank ability card so you can define a starting power, locked future power, prerequisite, and cost."],
  ["#sendButton", "Submit the typed player input. If the text box is empty, this acts as Continue and lets the LLM advance the scene."],
  ["#continueButton", "Ask the LLM to continue the current scene without adding a player action."],
  ["#suggestButton", "Ask the LLM for three concise player-input suggestions based on the current scene and known world state."],
  ["#regenSuggestionsButton", "Regenerate the three suggestions, optionally using the instruction typed beside this button."],
  ["#newGameButton", "Return to setup so you can start a new playthrough. This does not erase exported files."],
  ["#regenerateButton", "Restore the latest pre-turn snapshot and ask the LLM to rewrite that same opening, player, or continue response."],
  ["#rewindButton", "Rewind to the latest saved rewind point, usually the previous turn snapshot."],
  ["#exportButton", "Download the current world state as JSON so it can be backed up or imported later."],
  ["#importButton", "Choose a previously exported world JSON file and load it into the app."],
  ["#modelButton", "Open the model/settings tab in the side panel during play."],
  ["#refreshButton", "Reload the current world state from the backend without taking a turn."],
  ["#closeModelModal", "Close the LLM settings dialog without changing any unsaved values."],
  ["#closeEntityMenu", "Close the selected entity details panel."],
  ["#insertEntityRef", "Insert the selected entity reference token into the player input box."],
  ["#aliasForm button[type='submit']", "Save an alias for the selected indexed entity, making future references easier to recognize."],
  ["#playerAliasForm button[type='submit']", "Create an in-game alias for the player after play has started. It gets its own reputation track."],
  [".playerAliasActivate", "Use this player alias in gameplay. Its reputation is tracked separately from the true identity."],
  [".playerAliasDeactivate", "Stop using the active player alias."],
  [".playerAliasStateForm button[type='submit']", "Save whether the alias is protected by the worn disguise or presentation described here."],
  ["#modelForm button[type='submit']", "Save the selected model path and server URL used by the app."],
  [".selectModelFile", "Open a file picker to choose a local GGUF model file."],
  [".browseBackendRoot", "Open a folder picker to choose your Forge or ComfyUI install directory (any path you own)."],
  [".allowSearchRoot", "Scan common locations for Forge/Comfy installs (consented). You can still Browse or paste any folder."],
  [".testModelConnection", "Check whether the configured local LLM server is reachable and listing models."],
  ["#searchForm button[type='submit']", "Search indexed world memory for matching player, location, NPC, item, event, and journal facts."],
  [".useSuggestionButton", "Copy this suggestion into the player input box. It does not submit the turn until you press Send."],
  [".rewindPointButton", "Rewind to this specific saved turn snapshot."],
  [".insertRefButton", "Insert this entity reference token into the player input box."],
  [".randomizeOneAbility", "Replace this single ability card with a local preset."],
  [".addAbilityAfter", "Insert a blank ability card directly below this one."],
  [".removeAbility", "Remove this ability card from the starting setup."],
  ["[data-text-ai-open]", "Open a prompt box for this text field. The AI knows the field name, current setup context, and ability name when present."],
  ["[data-text-ai-fill]", "Fill the target text field from your prompt. If Optimize is checked, the app drafts first, then rewrites the draft."],
  ["[data-text-ai-close]", "Close this AI fill prompt without changing the target field."],
];

const RANDOM_GROUP_HELP = {
  character: "Randomize character-related setup fields, including past, memory rules, name, title, and abilities.",
  world: "Randomize setting fields, including genre, magic, races, economy, start location, and race rules.",
  people: "Randomize social-world pressure, factions, quest style, NPC density, NPC ranks, and skill frequency.",
  rules: "Randomize progression, risk, death, leveling, systems, skills, proficiency rules, and narration detail.",
};

const SETUP_STEP_HELP = [
  "Identity: name, portrait, titles, age, sex, backstory mode, and memory rules.",
  "Powers: optional starting special abilities and origin (none / acquired / innate).",
  "World: genre, map generation, start location, races, magic, technology, tone, and setting constraints.",
  "People: NPC density, quest style, factions, rank scale, and how trained NPCs tend to be.",
  "Rules: difficulty, death, narration detail, loot, inventory, leveling, skills, and in-world system UI.",
  "Checks: optional dice rolls for speech, strength, lore, events, and encounters.",
];

const TAB_HELP = {
  player: "Show player stats, identity, skills, abilities, karma, rewind points, and model budget info.",
  inventory: "Show carried items, equipped slots, weight, packed slots, rarity, enchantments, and storage pressure.",
  bible: "Show a compact world bible: active location, player summary, important NPCs, events, and journal highlights.",
  search: "Search the indexed world memory for references, facts, and tracked entities.",
  model: "View and edit local model connection settings while the game is running.",
  npcs: "Browse indexed NPCs from known locations, including role, race, rank, attitude, and trust.",
  items: "Browse tracked inventory and item records.",
  places: "Browse indexed locations and their visit counts or known NPCs.",
  events: "Browse tracked events, statuses, and links to locations or NPCs.",
  talk: "Browse summarized conversations with NPCs.",
  drafts: "Browse saved response-draft checks, DCs, verdicts, and verification notes.",
};

/** Play-mode tab categories for the side rail / dropdown nav */
const TAB_CATEGORIES = [
  {
    id: "you",
    label: "You",
    hint: "Self",
    tabs: [
      { id: "player", label: "Player" },
      { id: "inventory", label: "Inventory" },
    ],
  },
  {
    id: "world",
    label: "World",
    hint: "Lore",
    tabs: [
      { id: "places", label: "Places" },
      { id: "items", label: "Items" },
      { id: "events", label: "Events" },
      { id: "bible", label: "Bible" },
    ],
  },
  {
    id: "people",
    label: "People",
    hint: "Social",
    tabs: [
      { id: "npcs", label: "NPCs" },
      { id: "talk", label: "Talk" },
    ],
  },
  {
    id: "tools",
    label: "Tools",
    hint: "Meta",
    tabs: [
      { id: "search", label: "Find" },
      { id: "drafts", label: "Checks" },
      { id: "model", label: "LLM" },
    ],
  },
];

let activeTabCategory = "you";
let tabNavMode = localStorage.getItem("morkyn-tab-nav-mode") || "side"; // side | menu

const TEXT_AI_OPTION_HELP = {
  optimize: "Draft first, then run a second rewrite pass that keeps the important facts while tightening the wording.",
  simplify: "Ask for simpler wording and cleaner sentence structure without deleting important constraints.",
  expand: "Ask for more useful detail, such as boundaries, examples, training paths, costs, or scene-ready specifics.",
  preserve_phrases: "Keep distinctive phrases and named terms from your prompt unless shortening them clearly preserves the same meaning.",
};

const ABILITY_FIELD_HELP = {
  name: "The ability name shown in setup and later player records.",
  locked: "Unlocked abilities are usable at the start. Locked abilities exist in setup but require the listed condition before use.",
  description: "The immutable base description of what this ability does. The model may discover details later, but should not rewrite this foundation.",
  prerequisites: "Optional unlock condition, training path, item, oath, event, or other requirement.",
  cost: "Optional drawback, cooldown, resource, injury, fatigue, debt, risk, or other limit on using the ability.",
  growth_math:
    "Playable growth calculation for this power: XP curves, rank thresholds, per-use XP × risk, soft caps, rank→bonus formulas. Randomize invents numbers; the DM applies them in play.",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function clipText(value, maxLength = 360) {
  const text = String(value ?? "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
}

function fallbackNoticeText(reason) {
  const text = String(reason || "").trim();
  const lower = text.toLowerCase();
  if (lower.includes("without narration text") || lower.includes("no usable narration") || lower.includes("did not include usable narration")) {
    return "The text above is deterministic fallback narration. The local model's JSON was rejected because it did not include usable narration text.";
  }
  if (lower.includes("connection refused") || lower.includes("no model response was generated")) {
    return "The text above is deterministic fallback narration. The local model server did not produce a usable response for this turn.";
  }
  if (text) return `The text above is deterministic fallback narration. The local model response could not be used: ${clipText(text, 260)}`;
  return "The text above is deterministic fallback narration because the local model response could not be used.";
}

function helpTextLabel(text) {
  return String(text || "help").replace(/\s+/g, " ").trim().slice(0, 70);
}

let activeHelpTarget = null;
let pinnedHelpTarget = null;
let helpTooltipEl = null;

function findAll(root, selector) {
  const results = [];
  if (root?.matches?.(selector)) results.push(root);
  root?.querySelectorAll?.(selector).forEach((item) => results.push(item));
  return results;
}

function helpTooltip() {
  if (helpTooltipEl) return helpTooltipEl;
  helpTooltipEl = document.createElement("div");
  helpTooltipEl.className = "globalHelpTooltip hidden";
  helpTooltipEl.setAttribute("role", "tooltip");
  document.body.append(helpTooltipEl);
  return helpTooltipEl;
}

function positionHelpTooltip(target) {
  const tooltip = helpTooltip();
  const rect = target.getBoundingClientRect();
  tooltip.classList.remove("hidden");
  const tooltipRect = tooltip.getBoundingClientRect();
  const margin = 12;
  const left = Math.min(window.innerWidth - tooltipRect.width - margin, Math.max(margin, rect.left));
  const below = rect.bottom + 7;
  const above = rect.top - tooltipRect.height - 7;
  const top = below + tooltipRect.height + margin <= window.innerHeight ? below : Math.max(margin, above);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function showHelpForTarget(target, options = {}) {
  const text = target?.dataset?.helpText;
  if (!target || !text) return;
  const tooltip = helpTooltip();
  tooltip.textContent = text;
  activeHelpTarget = target;
  if (options.pinned) pinnedHelpTarget = target;
  positionHelpTooltip(target);
  target.classList.add("helpTextActive");
}

function hideHelpTooltip(options = {}) {
  if (pinnedHelpTarget && !options.force) return;
  activeHelpTarget?.classList.remove("helpTextActive");
  activeHelpTarget = null;
  pinnedHelpTarget = null;
  helpTooltip()?.classList.add("hidden");
}

function ensureHelpForTarget(target, text, options = {}) {
  if (!target || !text || target.dataset.helpAttached === "true") return;
  target.dataset.helpAttached = "true";
  target.dataset.helpText = text;
  target.classList.add("helpText");
  if (!target.title) target.title = text;
  if (!target.matches("button, input, select, textarea, a, label, [tabindex]")) target.tabIndex = 0;
}

function closeHelpPopovers(exceptTarget = null) {
  if (exceptTarget && pinnedHelpTarget === exceptTarget) return;
  hideHelpTooltip({ force: true });
}

function toggleHelpPopover(target) {
  if (pinnedHelpTarget === target) {
    hideHelpTooltip({ force: true });
    return;
  }
  closeHelpPopovers();
  showHelpForTarget(target, { pinned: true });
}

function settingLabel(name) {
  const field = setupForm?.elements?.[name];
  const isGroup = typeof RadioNodeList !== "undefined" && field instanceof RadioNodeList;
  const control = isGroup ? field[0] : field;
  return control?.closest?.("label")?.querySelector("span")?.textContent?.trim() || name.replaceAll("_", " ");
}

function decorateFunctionHelp(root = document) {
  for (const [selector, text] of ACTION_HELP_TARGETS) {
    findAll(root, selector).forEach((target) => {
      const inline = target.matches?.("[data-text-ai-open]");
      ensureHelpForTarget(target, text, { mode: inline ? "inline" : "wrap" });
    });
  }

  findAll(root, "[data-randomize-group]").forEach((button) => {
    const group = button.dataset.randomizeGroup;
    const powersHelp =
      "Re-roll ability origin, ability cards (including Growth Math), and Custom Proficiencies. Not name/backstory.";
    ensureHelpForTarget(
      button,
      group === "powers" ? powersHelp : RANDOM_GROUP_HELP[group] || "Randomize this setup group while respecting locked fields.",
    );
  });

  findAll(root, "[data-randomize-field]").forEach((button) => {
    const name = button.dataset.randomizeField;
    ensureHelpForTarget(button, `Randomize only ${settingLabel(name)}. The model receives earlier setup context and locked fields are respected unless this direct button was clicked.`, { label: `Randomize ${settingLabel(name)}` });
  });

  findAll(root, "[data-lock-setting]").forEach((input) => {
    const name = input.dataset.lockSetting;
    const label = input.closest("label");
    const text = name === "special_abilities"
      ? "Lock the whole Special Abilities section so setup randomization does not replace the list."
      : `Lock ${settingLabel(name)} so group and full randomize actions skip it.`;
    ensureHelpForTarget(label, text, { label: `Lock ${settingLabel(name)}` });
  });

  findAll(root, "#lockAbilityCount").forEach((input) => {
    ensureHelpForTarget(input.closest("label"), "Lock only the number of ability cards. Ability randomization may still rewrite the cards, but it keeps this count.", { label: "Lock ability count" });
  });

  findAll(root, "[data-custom-gain]").forEach((input) => {
    const name = input.dataset.customGain;
    ensureHelpForTarget(input.closest("label"), `Enable a custom multiplier and note for ${settingLabel(name)}. The note is sent to the playthrough rules.`, { label: `Custom ${settingLabel(name)}` });
  });

  findAll(root, "[data-setup-step]").forEach((button) => {
    const index = Number(button.dataset.setupStep || 0);
    ensureHelpForTarget(button, SETUP_STEP_HELP[index] || "Jump to this setup step.");
  });

  findAll(root, "[data-tab]").forEach((button) => {
    ensureHelpForTarget(button, TAB_HELP[button.dataset.tab] || "Open this side-panel view.");
  });

  findAll(root, "[data-text-ai-option]").forEach((input) => {
    ensureHelpForTarget(input.closest("label"), TEXT_AI_OPTION_HELP[input.dataset.textAiOption] || "Toggle this AI fill option.", { label: input.dataset.textAiOption });
  });

  findAll(root, "[data-ability-field]").forEach((control) => {
    const key = control.dataset.abilityField;
    const text = ABILITY_FIELD_HELP[key];
    if (!text) return;
    if (control.type === "radio") {
      const fieldset = control.closest("fieldset");
      ensureHelpForTarget(fieldset?.querySelector("legend"), text, { mode: "after", label: "Ability state" });
      return;
    }
    const label = control.closest("label");
    ensureHelpForTarget(label, text, { label: textAiLabel(control) });
  });
}

function entityLabel(entity) {
  if (!entity) return "Unknown";
  return entity.name || entity.title || entity.code || "Unknown";
}

function getEntityMap() {
  const map = new Map();
  const add = (type, entity) => {
    if (!entity?.code) return;
    map.set(entity.code.toUpperCase(), { type, entity });
  };
  for (const location of state?.locations || []) {
    add("location", location);
    for (const npc of location.npcs || []) add("npc", npc);
  }
  for (const item of state?.inventory || []) add("item", item);
  for (const event of state?.events || []) add("event", event);
  return map;
}

function refToken(type, code) {
  return `${PREFIX[type] || ""}${code}`;
}

function linkifyText(value) {
  const text = escapeHtml(value ?? "");
  const map = getEntityMap();
  let html = text.replace(/\[\[([A-Z]+|L\d+|I\d+|E\d+)]]/gi, (_, rawCode) => {
    const code = rawCode.toUpperCase();
    const found = map.get(code);
    if (!found) return escapeHtml(rawCode);
    return `<button class="entityLink" data-code="${escapeHtml(code)}" type="button">${escapeHtml(entityLabel(found.entity))}</button>`;
  });

  html = html.replace(/\b(L\d+|I\d+|E\d+)\b/g, (rawCode) => {
    const found = map.get(rawCode.toUpperCase());
    if (!found) return rawCode;
    return `<button class="entityLink subtle" data-code="${escapeHtml(rawCode.toUpperCase())}" type="button">${escapeHtml(entityLabel(found.entity))}</button>`;
  });
  return html;
}

function paragraphs(text) {
  const value = String(text ?? "").trim();
  if (!value) return `<p class="empty">Empty.</p>`;
  return value
    .split(/\n+/)
    .filter(Boolean)
    .map((line) => `<p>${linkifyText(line)}</p>`)
    .join("");
}

function segmentsHtml(segments, fallbackText) {
  if (!Array.isArray(segments) || !segments.length) return paragraphs(fallbackText);
  return segments
    .map((segment, index) => {
      const label = segment?.label || `segment ${index + 1}`;
      return `
        <section class="responseSegment">
          <h3>${escapeHtml(label)}</h3>
          ${paragraphs(segment?.text || "")}
        </section>
      `;
    })
    .join("");
}

function turnNarrationText(turn) {
  const narration = String(turn?.narration || "").trim();
  if (narration) return narration;
  const segments = Array.isArray(turn?.narration_segments) ? turn.narration_segments : [];
  return segments
    .map((segment) => String(segment?.text || "").trim())
    .filter(Boolean)
    .join("\n\n");
}

function turnNarrationHtml(turn) {
  return `<article class="turnNarration">${paragraphs(turnNarrationText(turn) || "The world hesitates.")}</article>`;
}

function elapsedLabel(startedAt) {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function updateStartSplashHeartbeat(startedAt) {
  if (!startSplashHeartbeatText) return;
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const message = START_SPLASH_REASSURANCE[Math.floor(elapsedSeconds / 12) % START_SPLASH_REASSURANCE.length];
  if (startSplashHeartbeatTitle) startSplashHeartbeatTitle.textContent = elapsedSeconds >= 60 ? "Still working" : "Local model is working";
  startSplashHeartbeatText.textContent = `Elapsed ${elapsedLabel(startedAt)} - ${message}`;
}

function stopGenerationProgressPolling() {
  if (generationProgressTimer) {
    window.clearInterval(generationProgressTimer);
    generationProgressTimer = null;
  }
  generationProgressSeenLines = 0;
  generationProgressLastPreview = "";
}

async function pollGenerationProgress(options = {}) {
  try {
    const response = await fetch("/api/generation-progress", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    applyGenerationProgress(data, options);
  } catch {
    /* ignore poll errors while waiting */
  }
}

function applyGenerationProgress(data, options = {}) {
  if (!data || typeof data !== "object") return;
  const phase = String(data.phase || "").trim();
  const detail = String(data.detail || "").trim();
  const step = Number(data.step || 0);
  const total = Number(data.total_steps || 0);
  const phaseLabel = [phase, detail].filter(Boolean).join(" — ");
  if (startSplashPhase && phaseLabel) {
    const stepBit = total > 0 ? ` (${Math.min(step, total)}/${total})` : "";
    startSplashPhase.textContent = `${phaseLabel}${stepBit}`;
  }
  const lines = Array.isArray(data.lines) ? data.lines : [];
  if (options.logToSplash !== false && startSplashLog && lines.length > generationProgressSeenLines) {
    for (let i = generationProgressSeenLines; i < lines.length; i += 1) {
      addStartSplashLine(lines[i]);
    }
    generationProgressSeenLines = lines.length;
  }
  const waitText = document.querySelector("#turnWaitText");
  const waitPhase = document.querySelector("#turnWaitPhase");
  if (waitText && detail) {
    waitText.textContent = detail;
    waitText.dataset.livePhase = "1";
  }
  if (waitPhase && phaseLabel) waitPhase.textContent = phaseLabel;
  const preview = String(data.preview || "").trim();
  if (preview && preview !== generationProgressLastPreview) {
    generationProgressLastPreview = preview;
    if (startSplashDraft && options.updateSplashDraft !== false) {
      startSplashDraft.textContent = preview;
      startSplashDraft.classList.add("startSplashCursor");
      startSplashDraft.scrollTop = startSplashDraft.scrollHeight;
    }
    const waitPreview = document.querySelector("#turnWaitPreview");
    if (waitPreview) {
      waitPreview.textContent = preview;
      waitPreview.classList.remove("hidden");
    }
  }
}

function startGenerationProgressPolling(options = {}) {
  stopGenerationProgressPolling();
  generationProgressSeenLines = 0;
  generationProgressLastPreview = "";
  pollGenerationProgress(options);
  generationProgressTimer = window.setInterval(() => pollGenerationProgress(options), 900);
}

function clearTurnWaitTimer() {
  if (turnWaitTimer) {
    window.clearInterval(turnWaitTimer);
    turnWaitTimer = null;
  }
  stopGenerationProgressPolling();
  setGeneratingUi(false);
}

function updateTurnWaitPanel(startedAt, kind) {
  const elapsed = document.querySelector("#turnWaitElapsed");
  const text = document.querySelector("#turnWaitText");
  if (!elapsed || !text) return;
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const messages = TURN_WAIT_REASSURANCE[kind] || TURN_WAIT_REASSURANCE.turn;
  elapsed.textContent = `Elapsed ${elapsedLabel(startedAt)}`;
  // Only use rotating reassurance when server has not posted a real phase yet.
  if (!text.dataset.livePhase) {
    text.textContent = messages[Math.floor(elapsedSeconds / 10) % messages.length];
  }
}

function showTurnWaitPanel(title, kind = "turn") {
  clearTurnWaitTimer();
  setGeneratingUi(true);
  if (!latestOutput) return;
  const startedAt = Date.now();
  latestOutput.innerHTML = `
    <div class="turnWaitPanel" role="status" aria-live="polite">
      <div class="turnWaitPulse" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="turnWaitCopy">
        <strong>${escapeHtml(title)}</strong>
        <span id="turnWaitElapsed">Elapsed 0:00</span>
        <p id="turnWaitPhase" class="turnWaitPhase">Preparing…</p>
        <p id="turnWaitText"></p>
        <pre id="turnWaitPreview" class="turnWaitPreview hidden" aria-label="Live narration preview"></pre>
      </div>
    </div>
  `;
  updateTurnWaitPanel(startedAt, kind);
  turnWaitTimer = window.setInterval(() => updateTurnWaitPanel(startedAt, kind), 1000);
  startGenerationProgressPolling({ logToSplash: false, updateSplashDraft: false });
}

function clearStartSplashTimers() {
  startSplashTimers.forEach((timer) => window.clearTimeout(timer));
  startSplashTimers = [];
  if (startSplashHeartbeatTimer) {
    window.clearInterval(startSplashHeartbeatTimer);
    startSplashHeartbeatTimer = null;
  }
  stopGenerationProgressPolling();
}

function addStartSplashLine(text) {
  if (!startSplashLog || !text) return;
  const line = document.createElement("p");
  line.className = "startSplashLine";
  line.textContent = text;
  startSplashLog.append(line);
  startSplashLog.scrollTop = startSplashLog.scrollHeight;
}

function showStartSplash() {
  if (!startSplash) return;
  clearStartSplashTimers();
  setGeneratingUi(true);
  const startedAt = Date.now();
  startSplash.classList.remove("hidden");
  if (startSplashLog) startSplashLog.innerHTML = "";
  startSplashHeartbeat?.classList.remove("hidden");
  if (startSplashPhase) startSplashPhase.textContent = "Preparing…";
  updateStartSplashHeartbeat(startedAt);
  startSplashHeartbeatTimer = window.setInterval(() => updateStartSplashHeartbeat(startedAt), 1000);
  if (startSplashDraft) {
    startSplashDraft.textContent = "";
    startSplashDraft.classList.remove("startSplashCursor");
  }
  // Seed a few local lines; server progress replaces/extends them as soon as the request runs.
  const lines = [
    "Collecting setup rules and locked choices.",
    "Preparing the opening-scene context packet.",
  ];
  lines.forEach((line, index) => {
    startSplashTimers.push(window.setTimeout(() => addStartSplashLine(line), index * 400));
  });
  startGenerationProgressPolling({ logToSplash: true, updateSplashDraft: true });
}

function hideStartSplash() {
  clearStartSplashTimers();
  setGeneratingUi(false);
  if (startSplashDraft) startSplashDraft.classList.remove("startSplashCursor");
  startSplash?.classList.add("hidden");
}

function scenePlanLines(plan) {
  const focusPoints = Array.isArray(plan?.focus_points) ? plan.focus_points : [];
  return focusPoints
    .slice(0, 6)
    .map((point, index) => {
      const label = point?.kind || point?.type || `focus ${index + 1}`;
      const summary = point?.summary || point?.goal || point?.description || "scene focus selected";
      return `Focus ${index + 1}: ${label} - ${summary}`;
    });
}

function scenePlanHtml(plan) {
  const focusPoints = Array.isArray(plan?.focus_points) ? plan.focus_points.slice(0, 6) : [];
  const goal = String(plan?.goal || plan?.writing_goal || "").trim();
  if (!goal && !focusPoints.length) return "";
  const rows = focusPoints.map((point, index) => {
    const label = point?.kind || point?.type || `focus ${index + 1}`;
    const summary = point?.summary || point?.goal || point?.description || "scene focus selected";
    return `<li><span>${escapeHtml(label)}</span>${escapeHtml(summary)}</li>`;
  }).join("");
  return `
    <section class="scenePlan">
      <strong>Scene plan</strong>
      ${goal ? `<p>${escapeHtml(goal)}</p>` : ""}
      ${rows ? `<ul>${rows}</ul>` : ""}
    </section>
  `;
}

function streamTextToTargets(text, targets, onDone = null, options = {}) {
  if (turnStreamTimer) window.clearInterval(turnStreamTimer);
  const value = String(text || "").trim();
  if (!value) {
    targets.forEach((target) => {
      if (target) target.textContent = "";
    });
    onDone?.();
    return;
  }
  let index = 0;
  const intervalMs = Number(options.intervalMs || 24);
  const durationMs = Number(options.durationMs || 4200);
  const targetTicks = Math.max(80, Math.ceil(durationMs / intervalMs));
  const step = Math.max(1, Math.ceil(value.length / targetTicks));
  targets.forEach((target) => {
    if (target) target.textContent = "";
  });
  turnStreamTimer = window.setInterval(() => {
    index = Math.min(value.length, index + step);
    const partial = value.slice(0, index);
    targets.forEach((target) => {
      if (target) {
        target.textContent = partial;
        target.scrollTop = target.scrollHeight;
      }
    });
    if (index >= value.length) {
      window.clearInterval(turnStreamTimer);
      turnStreamTimer = null;
      onDone?.();
    }
  }, intervalMs);
}

function boolField(formData, name) {
  return formData.get(name) === "true";
}

function formerLifeSelected(formData = new FormData(setupForm)) {
  const text = [readSetupValue(formData, "backstory_mode"), readSetupValue(formData, "memory_policy"), formData.get("character_backstory") || ""].join(" ").toLowerCase();
  return ["reincarnated", "transmigrated", "former life", "former-life", "reborn"].some((marker) => text.includes(marker));
}

function finiteNumber(value, fallback) {
  const number = Number(String(value ?? "").replace(",", "."));
  return Number.isFinite(number) ? number : fallback;
}

function intField(formData, name, fallback, min, max) {
  const raw = formData.get(name);
  const number = Math.trunc(finiteNumber(raw === "" || raw === null ? fallback : raw, fallback));
  return Math.max(min, Math.min(max, number));
}

function textField(formData, name, fallback = "", limit = 120) {
  const value = formData.get(name);
  return String(value === null || value === undefined ? fallback : value).slice(0, limit);
}

function setupValueText(formData, name, fallback = "", limit = SETTING_LIMITS[name] || 120) {
  const value = readSetupValue(formData, name);
  return String(value === null || value === undefined ? fallback : value).slice(0, limit);
}

function choice(values) {
  return values[Math.floor(Math.random() * values.length)];
}

function setField(name, value) {
  const field = setupForm.elements[name];
  if (!field) return;
  const nextValue = name === "custom_skills" ? commaSeparatedPhrases(value) : value;
  clearCustomValue(name);
  clearGainCustom(name);
  const isCheckboxGroup =
    (typeof RadioNodeList !== "undefined" && field instanceof RadioNodeList && field[0]?.type === "checkbox") ||
    field[0]?.type === "checkbox";
  if (isCheckboxGroup) {
    const values = Array.isArray(nextValue) ? nextValue : [String(nextValue)];
    Array.from(field).forEach((input) => {
      input.checked = values.includes(input.value);
    });
    updateCustomControls();
    return;
  }
  const isRadioGroup =
    (typeof RadioNodeList !== "undefined" && field instanceof RadioNodeList) || field[0]?.type === "radio";
  if (isRadioGroup) {
    const radio = Array.from(field).find((input) => input.value === String(nextValue));
    if (radio) radio.checked = true;
    return;
  }
  field.value = nextValue;
  updateCustomControls();
}

let llmBusyStartedAt = 0;
let llmBusyElapsedTimer = null;
let llmBusyLabel = "";

function formatBusyElapsed(startedAt) {
  const sec = Math.max(0, Math.floor((Date.now() - (startedAt || Date.now())) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function isSetupViewVisible() {
  return Boolean(setupView && !setupView.classList.contains("hidden"));
}

function isGameViewVisible() {
  return Boolean(gameView && !gameView.classList.contains("hidden"));
}

function stopLlmBusyElapsed() {
  if (llmBusyElapsedTimer) {
    window.clearInterval(llmBusyElapsedTimer);
    llmBusyElapsedTimer = null;
  }
  llmBusyStartedAt = 0;
}

function tickLlmBusyElapsed() {
  if (!llmBusyStartedAt) return;
  const label = formatBusyElapsed(llmBusyStartedAt);
  const setupEl = document.querySelector("#setupLlmBusyElapsed");
  const chatEl = document.querySelector("#chatThinkingElapsed");
  if (setupEl) setupEl.textContent = `Elapsed ${label}`;
  if (chatEl) chatEl.textContent = `Elapsed ${label}`;
}

function startLlmBusyElapsed() {
  if (!llmBusyStartedAt) llmBusyStartedAt = Date.now();
  tickLlmBusyElapsed();
  if (llmBusyElapsedTimer) return;
  llmBusyElapsedTimer = window.setInterval(tickLlmBusyElapsed, 1000);
}

function showSetupLlmBusyModal(label = "Working with the model…") {
  const modal = document.querySelector("#setupLlmBusyModal");
  if (!modal) return;
  const title = document.querySelector("#setupLlmBusyTitle");
  const text = document.querySelector("#setupLlmBusyText");
  const low = String(label || "").toLowerCase();
  if (title) title.textContent = label || "Working with the model…";
  if (text) {
    if (low.includes("random")) {
      text.textContent =
        "The local model is filling setup fields. This can take a while — the UI is not frozen.";
    } else if (low.includes("abilit")) {
      text.textContent = "Re-rolling powers with the local model. Hang tight.";
    } else if (low.includes("fill") || low.includes("text") || low.includes("optim")) {
      text.textContent = "The local model is rewriting that field. Please wait.";
    } else {
      text.textContent = "Local LLM is working. Nothing is broken — large models can take a minute.";
    }
  }
  modal.hidden = false;
  modal.classList.remove("hidden");
  startLlmBusyElapsed();
}

function hideSetupLlmBusyModal() {
  const modal = document.querySelector("#setupLlmBusyModal");
  if (!modal) return;
  modal.hidden = true;
  modal.classList.add("hidden");
}

function showChatThinkingBanner(label = "Model is thinking…") {
  const banner = document.querySelector("#chatThinkingBanner");
  const block = document.querySelector(".chatOutputBlock");
  if (!banner) return;
  const title = document.querySelector("#chatThinkingTitle");
  const text = document.querySelector("#chatThinkingText");
  const low = String(label || "").toLowerCase();
  if (title) title.textContent = label || "Model is thinking…";
  if (text) {
    if (low.includes("continu")) {
      text.textContent = "Continuing the scene with your local model…";
    } else if (low.includes("suggest") || low.includes("regen") || low.includes("idea")) {
      text.textContent = "Gathering idea prompts from the model…";
    } else if (low.includes("regenerat")) {
      text.textContent = "Regenerating the last reply…";
    } else {
      text.textContent = "Local LLM is generating a reply. The interface is fine — please wait.";
    }
  }
  banner.hidden = false;
  banner.classList.remove("hidden");
  block?.classList.add("isThinking");
  document.body.classList.add("llmChatThinking");
  startLlmBusyElapsed();
}

function hideChatThinkingBanner() {
  const banner = document.querySelector("#chatThinkingBanner");
  const block = document.querySelector(".chatOutputBlock");
  if (banner) {
    banner.hidden = true;
    banner.classList.add("hidden");
  }
  block?.classList.remove("isThinking");
  document.body.classList.remove("llmChatThinking");
}

/** Keep setup modal + chat banner in sync with busy state. */
function syncLlmBusyChrome(label = "") {
  if (label) llmBusyLabel = label;
  const busy = aiBusy || setupRandomizationLocked();
  const useLabel = llmBusyLabel || label || "Working…";

  if (!busy) {
    hideSetupLlmBusyModal();
    hideChatThinkingBanner();
    stopLlmBusyElapsed();
    llmBusyLabel = "";
    return;
  }

  startLlmBusyElapsed();
  // Prefer setup modal on new-game; chat banner in play (start splash has its own UI).
  const splashOpen = startSplash && !startSplash.classList.contains("hidden");
  if (isSetupViewVisible() && !splashOpen) {
    showSetupLlmBusyModal(useLabel);
    hideChatThinkingBanner();
  } else if (isGameViewVisible() && !splashOpen) {
    hideSetupLlmBusyModal();
    showChatThinkingBanner(useLabel);
  } else {
    hideSetupLlmBusyModal();
    hideChatThinkingBanner();
  }
}

function setAiBusy(nextBusy, label = "AI is thinking...") {
  aiBusy = nextBusy;
  if (!nextBusy) clearTurnWaitTimer();
  document.body.classList.toggle("aiBusy", nextBusy);
  document.body.dataset.aiBusyLabel = nextBusy ? label : "";
  if (turnInput) turnInput.disabled = nextBusy;
  if (sendButton) sendButton.disabled = nextBusy;
  if (continueButton) continueButton.disabled = nextBusy;
  if (suggestButton) suggestButton.disabled = nextBusy;
  if (regenSuggestionsButton) regenSuggestionsButton.disabled = nextBusy;
  if (regenerateButton) regenerateButton.disabled = nextBusy;
  if (saveSetupSettingsButton) saveSetupSettingsButton.disabled = nextBusy;
  if (setupSettingsFile) setupSettingsFile.disabled = nextBusy;
  suggestionPanel?.querySelectorAll("button").forEach((button) => {
    button.disabled = nextBusy;
  });
  if (setupStartButton) setupStartButton.disabled = nextBusy;
  if (setupStartMobileButton) setupStartMobileButton.disabled = nextBusy;
  if (setupNextButton && setupStep === setupSections.length - 1) setupNextButton.disabled = nextBusy;
  updateTextOptimizeControls();
  syncLlmBusyChrome(nextBusy ? label : "");
}

function enqueueAiTask(task, label = "AI is thinking...") {
  const run = async () => {
    setAiBusy(true, label);
    try {
      return await task();
    } finally {
      setAiBusy(false);
    }
  };
  // Shared queue: LLM turns and image gen wait on each other in the browser too.
  aiQueue = aiQueue.catch(() => {}).then(run);
  return aiQueue;
}

/** Alias — image work must share the same queue as LLM turns. */
function enqueueGpuTask(task, label = "Working…") {
  return enqueueAiTask(task, label);
}

function setupRandomizationLocked() {
  return setupRandomizeLockDepth > 0;
}

function setSetupRandomizationLocked(locked, label = "Randomizing setup...") {
  setupRandomizeLockDepth = Math.max(0, setupRandomizeLockDepth + (locked ? 1 : -1));
  const isLocked = setupRandomizationLocked();
  setupForm.classList.toggle("setupRandomizing", isLocked);
  setupForm.dataset.randomizeLockLabel = isLocked ? label : "";
  if (isLocked) {
    setupForm.setAttribute("aria-busy", "true");
    if (setupForm.contains(document.activeElement)) document.activeElement.blur();
  } else {
    setupForm.removeAttribute("aria-busy");
  }
  if ("inert" in setupForm) setupForm.inert = isLocked;
  updateAbilityOriginControls();
  updateTextOptimizeControls();
  // Show logo modal even if this path runs without enqueueAiTask wrapping
  syncLlmBusyChrome(isLocked ? label : aiBusy ? llmBusyLabel || "Working…" : "");
}

function withSetupRandomizationLock(task, label = "Randomizing setup...", fallback = null, options = {}) {
  return async () => {
    setSetupRandomizationLocked(true, label);
    try {
      try {
        return await task();
      } catch (error) {
        if (!fallback) throw error;
        fallback(error);
        return null;
      }
    } finally {
      setSetupRandomizationLocked(false);
      if (options.updateConditionals) updateConditionalSetup();
    }
  };
}

function isSettingLocked(name) {
  return Boolean(setupForm.querySelector(`[data-lock-setting="${name}"]`)?.checked);
}

function lockedSettingNames() {
  return Array.from(setupForm.querySelectorAll("[data-lock-setting]:checked")).map((input) => input.dataset.lockSetting);
}

function abilityQuantityLocked() {
  return Boolean(lockAbilityCount?.checked);
}

function abilityOrigin() {
  const value = setupForm.querySelector('input[name="special_ability_origin"]:checked')?.value || "none";
  return ABILITY_ORIGINS.has(value) ? value : "none";
}

function setAbilityOrigin(value) {
  const origin = ABILITY_ORIGINS.has(value) ? value : "none";
  const radio = setupForm.querySelector(`input[name="special_ability_origin"][value="${origin}"]`);
  if (radio) radio.checked = true;
  updateAbilityOriginControls();
}

function abilityOriginLabel(value = abilityOrigin()) {
  if (value === "innate") return "Innate";
  if (value === "acquired") return "Acquired";
  return "None";
}

function abilityDefaultLocked() {
  return abilityOrigin() === "acquired";
}

function currentAbilitySlotCount() {
  return abilityList.querySelectorAll(".abilitySetupCard").length;
}

function fitAbilitiesToLockedCount(abilities) {
  if (!abilityQuantityLocked()) return abilities;
  const targetCount = currentAbilitySlotCount();
  const nextAbilities = abilities.slice(0, targetCount);
  while (nextAbilities.length < targetCount) nextAbilities.push(randomAbilityPreset());
  return nextAbilities;
}

function clearCustomValue(name) {
  const input = setupForm.querySelector(`[data-custom-input="${name}"], [data-list-custom="${name}"]`);
  if (input) input.value = "";
  updateCustomControls();
}

function clearGainCustom(name) {
  const toggle = setupForm.querySelector(`[data-custom-gain="${name}"]`);
  if (!toggle) return;
  toggle.checked = false;
  const slider = setupForm.querySelector(`[data-gain-slider="${name}"]`);
  const number = setupForm.querySelector(`[data-gain-number="${name}"]`);
  const note = setupForm.querySelector(`[data-gain-note="${name}"]`);
  if (slider) slider.value = "1";
  if (number) number.value = "1.00";
  if (note) note.value = "";
  updateGainControls();
}

function randomBool(chance = 0.5) {
  return Math.random() < chance;
}

function optionalIdentityFillChance(name) {
  const formData = new FormData(setupForm);
  const contextText = [
    readSetupValue(formData, "backstory_mode"),
    readSetupValue(formData, "memory_policy"),
    setupForm.elements.character_backstory?.value || "",
  ]
    .join(" ")
    .toLowerCase();
  let chance = OPTIONAL_IDENTITY_FILL_CHANCE[name] ?? 0.18;
  if (["reincarnated", "transmigrated", "former life", "another world", "reborn"].some((marker) => contextText.includes(marker))) {
    chance += name === "player_public_name" ? 0.12 : 0.16;
  }
  if (["hidden", "amnesia", "fragment", "nameless", "unknown"].some((marker) => contextText.includes(marker))) {
    chance += name === "player_public_name" ? 0.1 : 0.06;
  }
  if (name === "player_public_name" && ["known as", "called", "alias", "nickname", "handle", "false name"].some((marker) => contextText.includes(marker))) {
    chance += 0.24;
  }
  if (name === "player_title" && ["title", "rank", "emperor", "empress", "king", "queen", "lord", "lady", "general", "commander", "champion", "hero", "saint", "archmage", "sect master", "elder", "ascendant", "s-rank", "mythic"].some((marker) => contextText.includes(marker))) {
    chance += 0.32;
  }
  return Math.min(chance, 0.68);
}

function rollInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function applyRandomizedSetup(payload) {
  const fields = payload?.fields || payload || {};
  Object.entries(fields).forEach(([name, value]) => {
    if (value === null || value === undefined) return;
    if (value === "" && !OPTIONAL_IDENTITY_FIELDS.has(name)) return;
    if (setupForm.querySelector(`[data-list-setting="${name}"]`)) {
      setListCustomValue(name, listValueText(value));
      return;
    }
    if (typeof value === "boolean") {
      setField(name, String(value));
      return;
    }
    const field = setupForm.elements[name];
    if (field?.tagName === "SELECT") {
      const optionValues = Array.from(field.options).map((option) => option.value);
      if (optionValues.includes(String(value))) {
        setField(name, String(value));
      } else {
        setField(name, "custom");
        const custom = setupForm.querySelector(`[data-custom-input="${name}"]`);
        if (custom) custom.value = String(value);
      }
      return;
    }
    setField(name, String(value));
  });

  const abilities = Array.isArray(payload?.special_abilities)
    ? payload.special_abilities
    : Array.isArray(fields?.special_abilities)
      ? fields.special_abilities
      : null;
  if (abilities) {
    const nextAbilities = fitAbilitiesToLockedCount(abilities);
    abilityList.innerHTML = "";
    nextAbilities.forEach((ability) => addAbility(ability));
  }
  normalizeRandomizerDependencies();
}

function commaSeparatedPhrases(value) {
  const raw = Array.isArray(value) ? value.join(",") : String(value || "");
  const normalized = raw.replace(/[\r\n;|]+/g, ",");
  const seen = new Set();
  const parts = [];
  normalized.split(",").forEach((part) => {
    const clean = part
      .trim()
      .replace(/^[-*]\s+/, "")
      .replace(/^\d+[.)]\s+/, "")
      .trim();
    const key = clean.toLowerCase();
    if (!clean || seen.has(key)) return;
    seen.add(key);
    parts.push(clean);
  });
  return parts.join(", ").slice(0, SETTING_LIMITS.custom_skills || 800);
}

function setupNamedControls() {
  return Array.from(setupForm.querySelectorAll("input[name], select[name], textarea[name]")).filter((control) => {
    if (control.closest(".abilitySetupCard")) return false;
    if (["button", "file", "hidden", "reset", "submit"].includes(control.type)) return false;
    return Boolean(control.name);
  });
}

function collectSetupSettings() {
  return {
    format: SETUP_SETTINGS_FORMAT,
    saved_at: new Date().toISOString(),
    setup_step: setupStep,
    controls: setupNamedControls().map((control) => ({
      name: control.name,
      tag: control.tagName.toLowerCase(),
      type: control.type || "",
      value: control.name === "custom_skills" ? commaSeparatedPhrases(control.value) : control.value,
      checked: Boolean(control.checked),
    })),
    custom_inputs: Array.from(setupForm.querySelectorAll("[data-custom-input]")).map((control) => ({
      name: control.dataset.customInput,
      value: control.value,
    })),
    list_custom: Array.from(setupForm.querySelectorAll("[data-list-custom]")).map((control) => ({
      name: control.dataset.listCustom,
      value: control.value,
    })),
    gain_controls: Array.from(setupForm.querySelectorAll("[data-gain-control]")).map((control) => {
      const name = control.dataset.gainControl;
      return {
        name,
        custom: Boolean(setupForm.querySelector(`[data-custom-gain="${name}"]`)?.checked),
        slider: setupForm.querySelector(`[data-gain-slider="${name}"]`)?.value || "1",
        number: setupForm.querySelector(`[data-gain-number="${name}"]`)?.value || "1.00",
        note: setupForm.querySelector(`[data-gain-note="${name}"]`)?.value || "",
      };
    }),
    locks: lockedSettingNames(),
    ability_origin: abilityOrigin(),
    ability_count_locked: abilityQuantityLocked(),
    abilities: Array.from(abilityList.querySelectorAll(".abilitySetupCard")).map(abilityCardSnapshot).filter(Boolean),
    // Session theme / last Randomize intent so Start bias survives save/load.
    randomize_idea: setupRandomizeIdea(),
    compose_intent: lastComposeIntent && typeof lastComposeIntent === "object" ? lastComposeIntent : null,
    session_theme: lastSessionTheme && typeof lastSessionTheme === "object" ? lastSessionTheme : null,
  };
}

function saveSetupSettings() {
  const customSkills = setupForm.elements.custom_skills;
  if (customSkills) customSkills.value = commaSeparatedPhrases(customSkills.value);
  const payload = collectSetupSettings();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ai-rpg-setup-settings-${Date.now()}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setupControlsByName(name) {
  return setupNamedControls().filter((control) => control.name === name);
}

function setupControlByDataset(selector, datasetKey, value) {
  return Array.from(setupForm.querySelectorAll(selector)).find((control) => control.dataset[datasetKey] === value) || null;
}

function restoreNamedSetupControl(entry) {
  if (!entry || !entry.name) return;
  const controls = setupControlsByName(entry.name);
  if (!controls.length) return;
  if (["checkbox", "radio"].includes(entry.type)) {
    const target = controls.find((control) => control.type === entry.type && control.value === entry.value);
    if (target) target.checked = Boolean(entry.checked);
    return;
  }
  const target = controls[0];
  target.value = entry.name === "custom_skills" ? commaSeparatedPhrases(entry.value) : String(entry.value ?? "");
}

function restoreDatasetValues(selector, datasetKey, entries, normalizer = (value) => String(value ?? "")) {
  (Array.isArray(entries) ? entries : []).forEach((entry) => {
    const target = setupControlByDataset(selector, datasetKey, entry.name);
    if (target) target.value = normalizer(entry.value);
  });
}

function restoreGainControls(entries) {
  (Array.isArray(entries) ? entries : []).forEach((entry) => {
    if (!entry?.name) return;
    const toggle = setupControlByDataset("[data-custom-gain]", "customGain", entry.name);
    const slider = setupControlByDataset("[data-gain-slider]", "gainSlider", entry.name);
    const number = setupControlByDataset("[data-gain-number]", "gainNumber", entry.name);
    const note = setupControlByDataset("[data-gain-note]", "gainNote", entry.name);
    if (toggle) toggle.checked = Boolean(entry.custom);
    if (slider) slider.value = String(entry.slider ?? "1");
    if (number) number.value = String(entry.number ?? slider?.value ?? "1.00");
    if (note) note.value = String(entry.note ?? "");
  });
}

function restoreAbilitySettings(settings) {
  setAbilityOrigin(settings.ability_origin || abilityOrigin() || "none");
  if (lockAbilityCount) lockAbilityCount.checked = Boolean(settings.ability_count_locked);
  abilityList.innerHTML = "";
  if (abilityOrigin() !== "none") {
    (Array.isArray(settings.abilities) ? settings.abilities : []).forEach((ability) => {
      addAbility({
        name: ability.name || "",
        description: ability.description || "",
        locked: Boolean(ability.locked),
        prerequisites: ability.prerequisites || "",
        cost: ability.cost_mode === "custom" ? ability.cost || "" : ability.cost || ability.cost_mode || "no cost",
        growth_math: ability.growth_math || "",
      });
      const card = abilityList.lastElementChild;
      const costMode = card?.querySelector('[data-ability-field="cost_mode"]');
      const cost = card?.querySelector('[data-ability-field="cost"]');
      if (costMode && ability.cost_mode) costMode.value = ability.cost_mode;
      if (cost && ability.cost_mode === "custom") cost.value = ability.cost || "";
    });
  }
  updateAbilityOriginControls();
}

function restoreSetupSettings(settings) {
  if (!settings || typeof settings !== "object") throw new Error("Settings file did not contain a JSON object.");
  if (settings.format && settings.format !== SETUP_SETTINGS_FORMAT) throw new Error("Settings file format is not supported.");
  setupForm.querySelectorAll("[data-text-ai-panel]").forEach((panel) => panel.classList.remove("open"));
  (Array.isArray(settings.controls) ? settings.controls : []).forEach(restoreNamedSetupControl);
  restoreDatasetValues("[data-custom-input]", "customInput", settings.custom_inputs);
  restoreDatasetValues("[data-list-custom]", "listCustom", settings.list_custom);
  restoreGainControls(settings.gain_controls);
  const locks = new Set(Array.isArray(settings.locks) ? settings.locks : []);
  setupForm.querySelectorAll("[data-lock-setting]").forEach((input) => {
    input.checked = locks.has(input.dataset.lockSetting);
  });
  restoreAbilitySettings(settings);
  const customSkills = setupForm.elements.custom_skills;
  if (customSkills) customSkills.value = commaSeparatedPhrases(customSkills.value);
  // Restore Randomize idea + session theme / intent for playthrough bias.
  const ideaInput = document.querySelector("#randomizeSetupPrompt");
  if (ideaInput && settings.randomize_idea != null) {
    ideaInput.value = String(settings.randomize_idea || "").slice(0, 400);
  }
  lastComposeIntent =
    settings.compose_intent && typeof settings.compose_intent === "object" ? settings.compose_intent : null;
  lastSessionTheme =
    settings.session_theme && typeof settings.session_theme === "object" ? settings.session_theme : null;
  if (lastComposeIntent || lastSessionTheme) {
    renderIntentSummary(lastComposeIntent, lastSessionTheme, { source: "loaded settings" });
  } else {
    clearIntentSummary();
  }
  ensureTextAiControls(setupForm);
  updateConditionalSetup();
  decorateFunctionHelp(setupForm);
  if (Number.isInteger(settings.setup_step)) setSetupStep(Math.max(0, Math.min(setupSections.length - 1, settings.setup_step)));
}

async function loadSetupSettings(file) {
  const settings = JSON.parse(await file.text());
  restoreSetupSettings(settings);
}

function listValueText(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join(", ");
  }
  return String(value || "").trim();
}

function splitListText(value) {
  return listValueText(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function setListCustomValue(name, value) {
  const requestedValues = splitListText(value);
  const available = new Map(
    availableListValues(name)
      .filter((item) => !["random", "custom"].includes(item))
      .map((item) => [item.toLowerCase(), item]),
  );
  const selectedValues = [];
  const customValues = [];
  for (const requestedValue of requestedValues) {
    const knownValue = available.get(requestedValue.toLowerCase());
    if (knownValue && !selectedValues.includes(knownValue)) {
      selectedValues.push(knownValue);
    } else if (!customValues.some((item) => item.toLowerCase() === requestedValue.toLowerCase())) {
      customValues.push(requestedValue);
    }
  }
  const customText = customValues.join(", ");
  const inputs = Array.from(setupForm.querySelectorAll(`input[name="${name}"]`));
  inputs.forEach((input) => {
    input.checked = selectedValues.includes(input.value) || (input.value === "custom" && Boolean(customText));
  });
  const customToggle = setupForm.querySelector(`input[name="${name}"][value="custom"]`);
  const customInput = setupForm.querySelector(`[data-list-custom="${name}"]`);
  if (customToggle) customToggle.checked = Boolean(customText);
  if (customInput) customInput.value = customText;
  updateCustomControls();
}

function availableListValues(name) {
  return Array.from(setupForm.querySelectorAll(`input[name="${name}"]`))
    .map((input) => input.value)
    .filter(Boolean);
}

function randomListSelection(name) {
  const values = availableListValues(name);
  const nonUtility = values.filter((value) => value !== "random" && value !== "custom");
  const rollPool = [...nonUtility];
  if (!rollPool.length) return [];
  const count = rollInt(1, rollPool.length);
  const picked = [];
  const pool = [...rollPool];
  for (let i = 0; i < count && pool.length; i += 1) {
    const index = rollInt(0, pool.length - 1);
    picked.push(pool.splice(index, 1)[0]);
  }
  return picked;
}

function fallbackRandomizeListField(name) {
  const picked = randomListSelection(name);
  if (!picked.length) return;
  setListCustomValue(name, picked.join(", "));
}

function availableSelectValues(name) {
  const field = setupForm.elements[name];
  if (!field?.options) return [];
  return Array.from(field.options)
    .map((option) => option.value)
    .filter((value) => value && !["random", "custom"].includes(value));
}

function availableRadioValues(name) {
  const field = setupForm.elements[name];
  const inputs = typeof RadioNodeList !== "undefined" && field instanceof RadioNodeList ? Array.from(field) : field?.type === "radio" ? [field] : [];
  return inputs.map((input) => input.value).filter(Boolean);
}

function fallbackRandomizeSelectField(name) {
  const values = availableSelectValues(name);
  if (!values.length) return false;
  setField(name, choice(values));
  return true;
}

function fallbackRandomizeRadioField(name) {
  const values = availableRadioValues(name);
  if (!values.length) return false;
  setField(name, choice(values));
  return true;
}

function fallbackRandomizeField(name, options = {}) {
  if (!options.ignoreLock && isSettingLocked(name)) return;
  if (OPTIONAL_IDENTITY_FIELDS.has(name) && !randomBool(optionalIdentityFillChance(name))) {
    setField(name, "");
    normalizeRandomizerDependencies();
    return;
  }
  if (name === "special_abilities") {
    if (abilityOrigin() === "none") {
      abilityList.innerHTML = "";
      normalizeRandomizerDependencies();
      return;
    }
    const previous = collectAbilities();
    const oneSkillish = (() => {
      const pf = lastComposeIntent?.power_fantasy || lastSessionTheme?.power_fantasy || {};
      const growth = String(pf.growth || "").toLowerCase();
      const start = String(pf.start_power || "").toLowerCase();
      return growth === "compounding" || start === "near_useless" || start === "weak";
    })();
    let count = abilityQuantityLocked()
      ? Math.max(1, currentAbilitySlotCount() || 1)
      : oneSkillish
        ? 1
        : rollInt(1, 5);
    abilityList.innerHTML = "";
    const used = [...previous];
    for (let i = 0; i < count; i += 1) {
      const next = randomAbilityPreset(used);
      used.push(next);
      addAbility(next);
    }
  } else if (setupForm.querySelector(`[data-list-setting="${name}"]`)) {
    fallbackRandomizeListField(name);
  } else if (!fallbackRandomizeRadioField(name) && !fallbackRandomizeSelectField(name) && RANDOM_SETUP[name]) {
    setField(name, choice(RANDOM_SETUP[name]));
  }
  normalizeRandomizerDependencies();
}

function fallbackRandomizeSequence(fields) {
  for (const name of fields) {
    normalizeRandomizerDependencies();
    if (!randomizeFieldApplies(name)) continue;
    fallbackRandomizeField(name);
  }
  // Full/group fallback finished → rebuild engine art prompts once.
  rebuildEnginePrompts({ force: true, silent: false }).catch(() => {});
}

function fieldContext(name) {
  if (OPTIONAL_IDENTITY_FIELDS.has(name)) {
    const formData = new FormData(setupForm);
    return {
      type: "optional_identity",
      value: setupForm.elements[name]?.value || "",
      fill_chance: optionalIdentityFillChance(name),
      backstory_mode: readSetupValue(formData, "backstory_mode"),
      memory_policy: readSetupValue(formData, "memory_policy"),
      roll_rule: "Blank is the normal result. Fill only when the current backstory and Backstory Mode make this optional identity useful.",
    };
  }
  const fieldset = setupForm.querySelector(`[data-list-setting="${name}"]`);
  if (fieldset) {
    const options = Array.from(fieldset.querySelectorAll(`input[name="${name}"]`)).map((input) => ({
      value: input.value,
      label: input.closest("label")?.textContent?.trim() || input.value,
      checked: input.checked,
      utility: ["random", "custom"].includes(input.value),
    }));
    return {
      type: "multi_select",
      options,
      selected_values: options.filter((option) => option.checked && !option.utility).map((option) => option.value),
      random_selected: options.some((option) => option.value === "random" && option.checked),
      custom_selected: options.some((option) => option.value === "custom" && option.checked),
      custom_text: setupForm.querySelector(`[data-list-custom="${name}"]`)?.value.trim() || "",
      roll_rule: "Roll option count from 1 to option count. If random is rolled, generate a coherent custom result. If custom is rolled, use custom_text when present.",
    };
  }
  const field = setupForm.elements[name];
  if (field?.tagName === "SELECT") {
    return {
      type: "select",
      options: Array.from(field.options).map((option) => ({ value: option.value, label: option.textContent })),
      selected_value: field.value,
      random_selected: field.value === "random",
      custom_selected: field.value === "custom",
      custom_text: setupForm.querySelector(`[data-custom-input="${name}"]`)?.value.trim() || "",
    };
  }
  if (name === "special_abilities") {
    const origin = abilityOrigin();
    return {
      type: "special_abilities",
      ability_origin: origin,
      origin_label: abilityOriginLabel(origin),
      existing_count: abilityList.querySelectorAll(".abilitySetupCard").length,
      quantity_locked: abilityQuantityLocked(),
      requested_count: currentAbilitySlotCount(),
      roll_rule: origin === "none"
        ? "Return an empty special_abilities list. No special abilities are defined at setup."
        : abilityQuantityLocked()
          ? "Generate exactly requested_count ability slots. Randomize content only; do not change quantity."
          : `Roll a fair count from 1 to 5. ${origin === "innate" ? "Abilities should usually be usable at the start and described as inherent, inherited, racial, bodily, soul-deep, or otherwise innate." : "Abilities should usually be locked or have prerequisites because they are acquired through play, training, events, systems, vows, tools, or former-life recovery."}`,
    };
  }
  return { type: "field", value: setupForm.elements[name]?.value || "" };
}

function setupSnapshotValue(formData, name) {
  if (setupForm.querySelector(`[data-list-setting="${name}"]`)) return readListSetting(formData, name, "");
  if (name === "special_abilities") return collectAbilities();
  if (["race_magic_enabled", "proficiency_system", "skill_levels_enabled", "leveling_system", "game_system"].includes(name)) return boolField(formData, name);
  if (["player_name", "player_public_name", "player_title", "player_age", "previous_life_age", "character_backstory", "hair", "facial_features", "appearance", "starter_equipment", "start_location", "custom_style", "race_magic_rules", "race_ability_rules", "custom_skills", "inventory_rules"].includes(name)) {
    return formData.get(name) || "";
  }
  if (["inventory_weight_limit", "inventory_slot_limit"].includes(name)) return Number(formData.get(name) || 0);
  return readSetupValue(formData, name);
}

function currentSetupSnapshot(activeField = "") {
  const formData = new FormData(setupForm);
  const activeIndex = RANDOM_FIELD_ORDER.indexOf(activeField);
  const lockedFields = lockedSettingNames();
  const snapshot = {
    _locked_fields: lockedFields,
    _locked_values: {},
    _locked_field_context: {},
    _active_field: activeField,
    _included_fields: [],
    _field_context: activeField ? fieldContext(activeField) : null,
  };
  RANDOM_FIELD_ORDER.forEach((name, index) => {
    if (activeField && activeIndex !== -1 && index > activeIndex) return;
    snapshot[name] = setupSnapshotValue(formData, name);
    snapshot._included_fields.push(name);
  });
  lockedFields.forEach((name) => {
    snapshot._locked_values[name] = setupSnapshotValue(formData, name);
    snapshot._locked_field_context[name] = fieldContext(name);
  });
  return snapshot;
}

function randomizeFieldApplies(name, formData = new FormData(setupForm)) {
  if (["race_magic_rarity", "race_magic_rules"].includes(name) && !boolField(formData, "race_magic_enabled")) return false;
  if (name === "system_style" && !boolField(formData, "game_system")) return false;
  if (["proficiency_access", "proficiency_growth_speed"].includes(name) && !boolField(formData, "proficiency_system")) return false;
  if (name === "xp_growth_speed" && !boolField(formData, "leveling_system")) return false;
  if (["previous_life_age", "previous_life_sex"].includes(name) && !formerLifeSelected(formData)) return false;
  if (name === "special_abilities" && abilityOrigin() === "none") return false;
  return true;
}

function normalizeRandomizerDependencies() {
  const formData = new FormData(setupForm);
  if (!boolField(formData, "race_magic_enabled")) {
    setField("race_magic_rarity", "same as world magic");
    const raceMagicRules = setupForm.elements.race_magic_rules;
    if (raceMagicRules) raceMagicRules.value = "";
  }
  if (!boolField(formData, "game_system")) setField("system_style", "subtle blue-window system");
  if (!boolField(formData, "proficiency_system")) setField("proficiency_access", "only expert tasks require training");
  if (!boolField(formData, "leveling_system")) setField("xp_growth_speed", "normal");
  if (abilityOrigin() === "none") abilityList.innerHTML = "";
  updateConditionalSetup();
}

async function randomizeGroup(group) {
  const fields = RANDOM_GROUPS[group] || [];
  const idea = setupRandomizeIdea();
  const intent = lastComposeIntent;
  for (const name of fields) {
    normalizeRandomizerDependencies();
    if (!randomizeFieldApplies(name)) continue;
    // Powers / character rolls should still feel the director seed
    await randomizeField(name, idea || intent ? { idea, intent } : {});
  }
  // Character / world / powers randomize finished → refresh engine image prompts once.
  if (group === "character" || group === "world" || group === "powers") {
    await rebuildEnginePrompts({ force: true, silent: false }).catch(() => {});
  }
}

function setupRandomizeIdea() {
  return String(document.querySelector("#randomizeSetupPrompt")?.value || "").trim().slice(0, 400);
}

async function randomizeField(name, options = {}) {
  if (!options.ignoreLock && isSettingLocked(name)) return;
  const current = currentSetupSnapshot(name);
  const idea = String(options.idea || "").trim().slice(0, 400);
  if (idea) current._randomize_idea = idea;
  const intent = options.intent || lastComposeIntent;
  if (intent && typeof intent === "object") current._compose_intent = intent;
  const response = await fetch("/api/randomize-setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group: `field:${name}`, current }),
  });
  if (!response.ok) throw new Error(await response.text());
  applyRandomizedSetup(await response.json());
}

async function ensureComposerOrder() {
  try {
    const response = await fetch("/api/setup/composer");
    if (!response.ok) return;
    const payload = await response.json();
    if (Array.isArray(payload.field_order) && payload.field_order.length) {
      RANDOM_FIELD_ORDER = payload.field_order;
    }
  } catch {
    /* keep built-in order */
  }
}

async function composeSetupIntent(idea) {
  const ideaText = String(idea || setupRandomizeIdea() || "").trim().slice(0, 400);
  const lockedFields = lockedSettingNames();
  const current = {
    _locked_fields: lockedFields,
    _locked_values: {},
  };
  lockedFields.forEach((name) => {
    current._locked_values[name] = setupSnapshotValue(new FormData(setupForm), name);
    current[name] = current._locked_values[name];
  });
  const response = await fetch("/api/setup/compose-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea: ideaText, current }),
  });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  lastComposeIntent = payload.intent || null;
  lastSessionTheme = payload.session_theme || null;
  if (Array.isArray(payload.field_order) && payload.field_order.length) {
    RANDOM_FIELD_ORDER = payload.field_order;
  }
  return payload;
}

function textAiKey(control) {
  if (!control) return "";
  if (control.dataset.abilityField) return `ability_${control.dataset.abilityField}`;
  if (control.dataset.gainNote) return `${control.dataset.gainNote}_note`;
  if (control.dataset.listCustom) return control.dataset.listCustom;
  if (control.dataset.customInput) return control.dataset.customInput;
  return control.name || "";
}

function textAiBaseField(control) {
  if (control?.dataset.abilityField) return "special_abilities";
  return control?.dataset.gainNote || control?.dataset.listCustom || control?.dataset.customInput || control?.name || "";
}

function textAiLabel(control) {
  const label = control?.closest("label");
  return label?.querySelector("span")?.textContent?.trim() || textAiKey(control).replaceAll("_", " ");
}

function isTextAiControl(control) {
  if (!control || !control.matches("input, textarea")) return false;
  if (control.matches("textarea[data-ability-field], textarea[name], textarea[data-list-custom], textarea[data-custom-input], textarea[data-gain-note]")) return true;
  if (control.matches('input[data-ability-field="name"]')) return true;
  if (!control.name || control.tagName !== "INPUT") return false;
  return !["button", "checkbox", "color", "file", "hidden", "number", "radio", "range", "reset", "submit"].includes(control.type);
}

function abilityCardSnapshot(card) {
  if (!card) return null;
  const field = (name) => card.querySelector(`[data-ability-field="${name}"]`);
  const costMode = field("cost_mode")?.value || "no cost";
  return {
    name: field("name")?.value.trim() || "",
    description: field("description")?.value.trim() || "",
    locked: card.querySelector('[data-ability-field="locked"]:checked')?.value === "true",
    prerequisites: field("prerequisites")?.value.trim() || "",
    cost_mode: costMode,
    cost: costMode === "custom" ? field("cost")?.value.trim() || "" : costMode,
    growth_math: field("growth_math")?.value.trim() || "",
  };
}

function textAiPanelTemplate(label) {
  return `
    <div class="textAiPanel hidden" data-text-ai-panel>
      <textarea class="textAiPrompt" data-text-ai-prompt rows="3" maxlength="700" placeholder="Tell the AI what to write for ${escapeHtml(label)}."></textarea>
      <div class="textAiToggles" aria-label="AI fill options">
        <label><input type="checkbox" data-text-ai-option="optimize" /> Optimize</label>
        <label><input type="checkbox" data-text-ai-option="simplify" /> Simplify</label>
        <label><input type="checkbox" data-text-ai-option="expand" /> Add detail</label>
        <label><input type="checkbox" data-text-ai-option="preserve_phrases" checked /> Keep phrases</label>
      </div>
      <div class="textAiActions">
        <button class="miniButton" data-text-ai-fill type="button">Fill</button>
        <button class="miniButton" data-text-ai-close type="button">Close</button>
      </div>
    </div>
  `;
}

function ensureTextAiControls(root = setupForm) {
  root
    .querySelectorAll("input[name], textarea[name], textarea[data-list-custom], textarea[data-custom-input], textarea[data-gain-note], input[data-ability-field], textarea[data-ability-field]")
    .forEach((control) => {
      if (!isTextAiControl(control) || control.dataset.textAiAttached || !textAiKey(control)) return;
      const label = textAiLabel(control);
      const wrapper = document.createElement("div");
      wrapper.className = "textAiWrap";
      wrapper.dataset.textAiWrap = "true";
      control.insertAdjacentElement("beforebegin", wrapper);
      wrapper.append(control);
      control.dataset.textAiControl = "true";
      wrapper.insertAdjacentHTML(
        "beforeend",
        `<button class="textAiButton" data-text-ai-open type="button" aria-label="Fill ${escapeHtml(label)} with AI" title="Fill ${escapeHtml(label)} with AI">AI</button>`,
      );
      wrapper.insertAdjacentHTML("afterend", textAiPanelTemplate(label));
      control.dataset.textAiAttached = "true";
    });
  updateTextAiControls();
}

function updateTextAiControls() {
  setupForm.querySelectorAll(".textAiWrap").forEach((wrapper) => {
    const control = wrapper.querySelector("[data-text-ai-control]");
    const panel = wrapper.nextElementSibling?.matches("[data-text-ai-panel]") ? wrapper.nextElementSibling : null;
    const customHidden = control?.matches("[data-custom-input], [data-list-custom]") && !control.classList.contains("open");
    const gainHidden = control?.matches("[data-gain-note]") && control.disabled;
    const hidden = Boolean(customHidden || gainHidden);
    wrapper.classList.toggle("hidden", hidden);
    panel?.classList.toggle("hidden", hidden || !panel.classList.contains("open"));
    const button = wrapper.querySelector("[data-text-ai-open]");
    if (button) button.disabled = aiBusy || Boolean(control?.disabled);
    panel?.querySelectorAll("button, textarea, input").forEach((item) => {
      item.disabled = aiBusy || hidden;
    });
  });
}

function updateTextOptimizeControls() {
  updateTextAiControls();
}

function closeTextAiPanels(exceptPanel = null) {
  setupForm.querySelectorAll("[data-text-ai-panel]").forEach((panel) => {
    if (panel === exceptPanel) return;
    panel.classList.remove("open");
    panel.classList.add("hidden");
  });
}

function textAiOptions(panel) {
  const options = {};
  panel?.querySelectorAll("[data-text-ai-option]").forEach((input) => {
    options[input.dataset.textAiOption] = Boolean(input.checked);
  });
  return options;
}

function textAiSnapshot(control, field, promptText, options, stage, draftText = "") {
  const baseField = textAiBaseField(control);
  const activeField = RANDOM_FIELD_ORDER.includes(baseField) ? baseField : "";
  const snapshot = currentSetupSnapshot(activeField);
  const setupFieldContext = activeField ? fieldContext(activeField) : null;
  snapshot._text_ai_field = field;
  snapshot._text_ai_stage = stage;
  snapshot._user_prompt = promptText;
  snapshot._text_ai_options = options;
  snapshot._optimize_text = draftText || control.value.trim();
  snapshot._field_label = textAiLabel(control);
  snapshot._field_context = {
    type: "text_ai_fill",
    base_field: baseField,
    setup_field_context: setupFieldContext,
    field_label: snapshot._field_label,
    existing_text: control.value.trim(),
    related_name: control.closest(".abilitySetupCard")?.querySelector('[data-ability-field="name"]')?.value.trim() || snapshot.player_name || "",
    max_length: Number(control.maxLength) > 0 ? Number(control.maxLength) : null,
    placeholder: control.placeholder || "",
    control_tag: control.tagName.toLowerCase(),
  };
  const abilityCard = control.closest(".abilitySetupCard");
  if (abilityCard) snapshot._ability_context = abilityCardSnapshot(abilityCard);
  return snapshot;
}

function setTextAiControlValue(control, value) {
  let text = Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean).join(", ") : String(value || "").trim();
  if (control.name === "custom_skills") text = commaSeparatedPhrases(text);
  if (!text) throw new Error("AI returned no usable text.");
  const maxLength = Number(control.maxLength || 0);
  if (maxLength > 0) text = text.slice(0, maxLength);

  if (control.dataset.listCustom) {
    const name = control.dataset.listCustom;
    const customToggle = setupForm.querySelector(`input[name="${name}"][value="custom"]`);
    if (customToggle) customToggle.checked = true;
  }
  if (control.dataset.customInput) {
    const select = setupForm.elements[control.dataset.customInput];
    if (select) select.value = "custom";
  }
  if (control.dataset.gainNote) {
    const toggle = setupForm.querySelector(`[data-custom-gain="${control.dataset.gainNote}"]`);
    if (toggle) toggle.checked = true;
  }
  if (control.dataset.abilityField === "cost") {
    const costMode = control.closest("label")?.querySelector('[data-ability-field="cost_mode"]');
    if (costMode) costMode.value = "custom";
  }

  control.value = text;
  control.dispatchEvent(new Event("input", { bubbles: true }));
  updateCustomControls();
  updateGainControls();
  updateTextAiControls();
}

async function requestTextAiField(control, groupPrefix, promptText, options, stage, draftText = "") {
  const field = textAiKey(control);
  if (!field) throw new Error("Could not identify the text field to fill.");
  const response = await fetch("/api/randomize-setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group: `${groupPrefix}:${field}`, current: textAiSnapshot(control, field, promptText, options, stage, draftText) }),
  });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  const fields = payload?.fields || payload || {};
  return fields[field];
}

async function fillTextAiControl(control, panel) {
  const promptText = panel.querySelector("[data-text-ai-prompt]")?.value.trim() || "";
  const options = textAiOptions(panel);
  const draft = await requestTextAiField(control, "text", promptText, options, "draft");
  if (options.optimize) {
    const optimized = await requestTextAiField(control, "optimize", promptText, options, "optimize", String(draft || ""));
    setTextAiControlValue(control, optimized);
  } else {
    setTextAiControlValue(control, draft);
  }
}

function clearIntentSummary() {
  const el = document.querySelector("#setupIntentSummary");
  if (!el) return;
  el.hidden = true;
  el.innerHTML = "";
}

function intentSummaryBits(intent, theme) {
  const src = (intent && typeof intent === "object" ? intent : null) || {};
  const th = (theme && typeof theme === "object" ? theme : null) || {};
  const pf =
    (src.power_fantasy && typeof src.power_fantasy === "object" && src.power_fantasy) ||
    (th.power_fantasy && typeof th.power_fantasy === "object" && th.power_fantasy) ||
    {};
  const genre = String(src.genre || th.genre || "").trim();
  const adapter = String(src.adapter_hint || th.adapter_hint || "").trim();
  const tone = String(src.tone || th.tone || "").trim();
  const edge = String(src.edge || th.edge || "").trim();
  const difficulty = String(src.difficulty || "").trim();
  const dm = String(src.dm_stance || th.dm_stance || "").trim();
  const growth = String(pf.growth || "").trim();
  const startPower = String(pf.start_power || "").trim();
  const systemUi = pf.system_ui === true || pf.system_ui === "true";
  const isekai = !!(src.isekai || th.isekai);
  const skill = String(pf.skill_summary || "").trim();
  return {
    genre,
    adapter,
    tone,
    edge,
    difficulty,
    dm,
    growth,
    startPower,
    systemUi,
    isekai,
    skill,
  };
}

function humanizeIntentToken(raw) {
  return String(raw || "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function renderIntentSummary(intent, theme, options = {}) {
  const el = document.querySelector("#setupIntentSummary");
  if (!el) return;
  const bits = intentSummaryBits(intent, theme);
  const hasAny =
    bits.genre ||
    bits.adapter ||
    bits.growth ||
    bits.dm ||
    bits.isekai ||
    bits.difficulty ||
    bits.tone;
  if (!hasAny) {
    clearIntentSummary();
    return;
  }
  const chips = [];
  if (bits.isekai) chips.push(`<span class="intentChip"><em>Tag</em> isekai</span>`);
  if (bits.genre) {
    chips.push(`<span class="intentChip"><em>Genre</em> ${escapeHtml(humanizeIntentToken(bits.genre))}</span>`);
  }
  if (bits.difficulty) {
    chips.push(
      `<span class="intentChip"><em>Difficulty</em> ${escapeHtml(humanizeIntentToken(bits.difficulty))}</span>`,
    );
  }
  if (bits.tone) {
    chips.push(`<span class="intentChip"><em>Tone</em> ${escapeHtml(humanizeIntentToken(bits.tone))}</span>`);
  }
  if (bits.startPower || bits.growth) {
    const growth = [bits.startPower, bits.growth]
      .filter(Boolean)
      .map(humanizeIntentToken)
      .join(" → ");
    chips.push(`<span class="intentChip"><em>Growth</em> ${escapeHtml(growth || "—")}</span>`);
  }
  if (bits.systemUi) chips.push(`<span class="intentChip"><em>UI</em> system windows</span>`);
  if (bits.edge) {
    chips.push(`<span class="intentChip"><em>Edge</em> ${escapeHtml(humanizeIntentToken(bits.edge))}</span>`);
  }
  if (bits.adapter && bits.adapter !== "default") {
    chips.push(
      `<span class="intentChip intentChipMuted"><em>Adapter</em> ${escapeHtml(humanizeIntentToken(bits.adapter))}</span>`,
    );
  }
  const source = options.source ? String(options.source) : "";
  el.hidden = false;
  el.removeAttribute("data-help-attached");
  el.classList.remove("helpText", "helpTextActive");
  el.innerHTML = `
    <div class="intentSummaryHead">
      <strong class="intentSummaryTitle" id="intentSummaryHelpTarget" tabindex="0">Compiled plan</strong>
      <span class="muted intentSummarySub">Session theme after Randomize${source ? ` · ${escapeHtml(source)}` : ""}</span>
    </div>
    <div class="intentChipRow">${chips.join("") || `<span class="muted">No genre lean</span>`}</div>
    <div class="intentSummaryLines">
      ${
        bits.dm
          ? `<p class="intentDm"><span class="intentLineLabel">DM</span><span class="intentLineBody">${escapeHtml(humanizeIntentToken(bits.dm))}</span></p>`
          : ""
      }
      ${
        bits.skill
          ? `<p class="intentSkill"><span class="intentLineLabel">Skill</span><span class="intentLineBody">${escapeHtml(humanizeIntentToken(bits.skill))}</span></p>`
          : ""
      }
    </div>
  `;
  // Help only on the title, not the whole bar (avoids dotted underline + huge hit area).
  const helpTarget = el.querySelector("#intentSummaryHelpTarget");
  if (helpTarget) {
    ensureHelpForTarget(
      helpTarget,
      "After Randomize (or Load Settings), this is the compiled genre / system / growth / DM plan stored as the session theme.",
    );
  }
}

function renderDirectorPresets() {
  const host = document.querySelector("#directorPresets");
  if (!host || host.dataset.ready === "1") return;
  host.dataset.ready = "1";
  host.innerHTML = DIRECTOR_PRESETS.map(
    (p) =>
      `<button type="button" class="chipBtn secondaryButton directorPreset" data-director-preset="${escapeHtml(p.id)}" title="${escapeHtml(p.idea)}">${escapeHtml(p.label)}</button>`,
  ).join("");
}

function applyDirectorPreset(presetId, { runRandomize = true } = {}) {
  const preset = DIRECTOR_PRESETS.find((p) => p.id === presetId);
  if (!preset) return;
  const ideaInput = document.querySelector("#randomizeSetupPrompt");
  if (ideaInput) ideaInput.value = preset.idea.slice(0, 400);
  if (runRandomize) randomizeSetup?.click();
}

async function randomizeAllSetup(options = {}) {
  const idea = String(options.idea || setupRandomizeIdea() || "").trim().slice(0, 400);
  await ensureComposerOrder();
  let intent = null;
  // Tree root: compile intent, apply deterministic overrides, then walk dependent fields.
  if (idea) {
    const composed = await composeSetupIntent(idea);
    intent = composed.intent || null;
    const overrides = composed.field_overrides || {};
    if (overrides && typeof overrides === "object" && Object.keys(overrides).length) {
      applyRandomizedSetup({ fields: overrides });
      normalizeRandomizerDependencies();
    }
    renderIntentSummary(lastComposeIntent, lastSessionTheme, { source: "from idea" });
  } else {
    lastComposeIntent = null;
    lastSessionTheme = null;
    clearIntentSummary();
  }
  for (const name of RANDOM_FIELD_ORDER) {
    normalizeRandomizerDependencies();
    if (!randomizeFieldApplies(name)) continue;
    // Skip fields already set by deterministic intent overrides (still re-roll unlocked if empty).
    if (intent && options.skipOverrideFields !== false) {
      // Always re-walk text-heavy / identity fields so LLM can enrich; keep hard overrides for enums/bools.
      const hardOverrideFields = new Set([
        "difficulty",
        "game_system",
        "leveling_system",
        "skill_levels_enabled",
        "skill_growth_speed",
        "proficiency_growth_speed",
        "xp_growth_speed",
        "new_skill_frequency",
        "special_ability_origin",
        "backstory_mode",
        "memory_policy",
        "death_rules",
        "loot_rarity",
        "world_style",
        "system_style",
        // custom_skills is intentionally NOT hard-skipped: ONE_SKILL_FRAME skeleton is expanded by LLM
        // Structure fields seeded clean from intent — do not let LLM re-paste growth slogans.
        "quest_style",
        "faction_pressure",
        "economy",
        "npc_stat_scaling",
        "npc_skill_frequency",
        "world_races",
        "rank_scale",
        "skill_style",
        // Checks friction for system/isekai seeds
        "dice_checks_enabled",
        "check_difficulty",
        "event_check_frequency",
        "encounter_check_frequency",
        "unskilled_mishaps",
        "auto_check_on_risky_actions",
        "show_rolls_in_ui",
      ]);
      if (hardOverrideFields.has(name) && !isSettingLocked(name)) {
        // Already applied via overrides; skip LLM so difficulty never becomes a slogan.
        const formData = new FormData(setupForm);
        const currentVal = setupSnapshotValue(formData, name);
        if (currentVal !== "" && currentVal !== null && currentVal !== undefined) continue;
      }
    }
    await randomizeField(name, idea ? { idea, intent } : { intent });
  }
  // Full-package coherence pass: LLM re-reads setup for tacky/AI-generic prose.
  // Locked fields win; slower but more coherent.
  if (options.coherencePass !== false) {
    try {
      syncLlmBusyChrome("Polishing setup for coherence…");
      await runSetupCoherencePass({ idea, intent });
    } catch (err) {
      console.warn("Coherence pass skipped", err);
    }
  }
  // Refresh summary after walk (intent may still be the pre-walk plan).
  if (idea && (lastComposeIntent || lastSessionTheme)) {
    renderIntentSummary(lastComposeIntent, lastSessionTheme, { source: "after Randomize" });
  }
  // Full randomize finished → rebuild face/body engine prompts once (overwrites prior).
  await rebuildEnginePrompts({ force: true, silent: false }).catch(() => {});
}

async function runSetupCoherencePass(options = {}) {
  const locked = lockedSettingNames();
  const formData = new FormData(setupForm);
  const current = {
    _locked_fields: locked,
    _randomize_idea: String(options.idea || setupRandomizeIdea() || "").slice(0, 400),
    _compose_intent: options.intent || lastComposeIntent,
  };
  // Full snapshot of reviewed fields
  const reviewKeys = [
    "character_backstory",
    "custom_style",
    "custom_skills",
    "race_magic_rules",
    "race_ability_rules",
    "inventory_rules",
    "start_location",
    "world_style",
    "tone",
    "quest_style",
    "faction_pressure",
    "system_style",
    "player_title",
    "player_public_name",
    "special_abilities",
    "special_ability_origin",
    "player_name",
    "backstory_mode",
    "memory_policy",
    "difficulty",
    "game_system",
    "skill_levels_enabled",
  ];
  reviewKeys.forEach((name) => {
    try {
      current[name] = setupSnapshotValue(formData, name);
    } catch (_) {
      /* ignore */
    }
  });
  current.special_abilities = collectAbilities();
  locked.forEach((name) => {
    current[name] = setupSnapshotValue(formData, name);
  });

  const response = await fetch("/api/setup/coherence-pass", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current,
      locked_fields: locked,
      intent: options.intent || lastComposeIntent,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  if (payload?.fields && Object.keys(payload.fields).length) {
    applyRandomizedSetup({ fields: payload.fields, special_abilities: payload.special_abilities });
  } else if (Array.isArray(payload?.special_abilities)) {
    applyRandomizedSetup({ special_abilities: payload.special_abilities });
  }
  normalizeRandomizerDependencies();
  if (payload?.notes && latestOutput) {
    // Soft note only on setup (latestOutput may be game view)
    const setupNote = document.querySelector("#setupIntentSummary");
    if (setupNote && !setupNote.hidden && payload.changed?.length) {
      const note = document.createElement("p");
      note.className = "intentCoherenceNote muted";
      note.textContent = `Coherence pass: ${payload.notes}`;
      setupNote.appendChild(note);
    }
  }
  return payload;
}

const SETUP_STEP_LABELS = ["Identity", "Powers", "World", "People", "Rules", "Checks"];

function setupStepLabel(index) {
  const name = SETUP_STEP_LABELS[index] || `Step ${index + 1}`;
  return `${index + 1} · ${name}`;
}

function closeSetupStepFlyout() {
  if (setupTourKeepFlyoutOpen) return;
  const nav = document.querySelector("#setupSteps");
  const toggle = document.querySelector("#setupNavToggle");
  const flyout = document.querySelector("#setupStepFlyout");
  if (!nav?.classList.contains("isFlyout")) return;
  flyout?.setAttribute("hidden", "");
  toggle?.setAttribute("aria-expanded", "false");
  nav.classList.remove("isOpen");
}

function openSetupStepFlyout() {
  const nav = document.querySelector("#setupSteps");
  const toggle = document.querySelector("#setupNavToggle");
  const flyout = document.querySelector("#setupStepFlyout");
  if (!nav?.classList.contains("isFlyout")) return;
  flyout?.removeAttribute("hidden");
  toggle?.setAttribute("aria-expanded", "true");
  nav.classList.add("isOpen");
}

/**
 * Mount step picker into the active section header (flyout), or beside sections (pinned rail).
 * Row: [2 · Powers ▾] [Pin]  description…  [Randomize …]
 */
function placeSetupStepsNav() {
  const nav = document.querySelector("#setupSteps");
  const panel = document.querySelector("#setupForm") || document.querySelector(".setupPanel");
  if (!nav || !panel) return;
  const sections = panel.querySelector(".setupSections");
  const pinned = nav.classList.contains("isPinned");

  if (pinned) {
    nav.classList.remove("isInlineInSection");
    // Restore as panel-level rail before sections
    if (sections && nav.parentElement !== panel) {
      panel.insertBefore(nav, sections);
    } else if (sections && nav.nextElementSibling !== sections) {
      panel.insertBefore(nav, sections);
    }
    return;
  }

  const host = panel.querySelector(".setupSection.active .sectionHeaderNav[data-setup-step-nav-host]");
  if (host) {
    if (nav.parentElement !== host) host.appendChild(nav);
    nav.classList.add("isInlineInSection");
  } else if (sections && nav.parentElement !== panel) {
    panel.insertBefore(nav, sections);
    nav.classList.remove("isInlineInSection");
  }
}

function applySetupNavMode(mode) {
  const nav = document.querySelector("#setupSteps");
  const panel = document.querySelector("#setupForm") || document.querySelector(".setupPanel");
  const pinBtn = document.querySelector("#setupNavPin");
  const preferPin = mode === "pin";
  // Phones never pin — always flyout overlay
  const canPin = window.matchMedia("(min-width: 900px)").matches;
  const pinned = preferPin && canPin;
  nav?.classList.toggle("isPinned", pinned);
  nav?.classList.toggle("isFlyout", !pinned);
  panel?.classList.toggle("setupNavPinned", pinned);
  panel?.classList.toggle("setupNavFlyout", !pinned);
  if (pinBtn) {
    pinBtn.textContent = pinned ? "Float" : "Pin";
    pinBtn.title = pinned
      ? "Use floating step dropdown (better for narrow layouts)"
      : "Pin steps to the side (wide screens)";
    pinBtn.hidden = !canPin;
  }
  if (pinned) {
    document.querySelector("#setupStepFlyout")?.removeAttribute("hidden");
    document.querySelector("#setupNavToggle")?.setAttribute("aria-expanded", "false");
    nav?.classList.remove("isOpen");
  } else {
    closeSetupStepFlyout();
  }
  placeSetupStepsNav();
  localStorage.setItem("morkyn-setup-nav-mode", pinned ? "pin" : "flyout");
}

function setSetupStep(nextStep) {
  setupStep = Math.max(0, Math.min(setupSections.length - 1, nextStep));
  setupSections.forEach((section, index) => section.classList.toggle("active", index === setupStep));
  document.querySelectorAll("[data-setup-step]").forEach((button) => {
    const idx = Number(button.dataset.setupStep);
    button.classList.toggle("active", idx === setupStep);
  });
  const label = document.querySelector("#setupNavTriggerLabel");
  if (label) label.textContent = setupStepLabel(setupStep);
  if (setupPrevButton) setupPrevButton.disabled = setupStep === 0;
  if (setupNextButton) setupNextButton.textContent = setupStep === setupSections.length - 1 ? "Start" : "Next";
  if (setupStepStatus) setupStepStatus.textContent = `Step ${setupStep + 1} of ${setupSections.length}`;
  placeSetupStepsNav();
  // In flyout mode, picking a step closes the menu so the form is usable again
  // (tour keeps flyout open while teaching the menu)
  if (!setupTourKeepFlyoutOpen) closeSetupStepFlyout();
}

function isNarrowSetupViewport() {
  return window.matchMedia("(max-width: 899.98px)").matches;
}

function setSetupMoreOpen(open) {
  if (!setupActionsMore || !setupMoreToggle) return;
  // Desktop always shows tools; ignore collapse
  if (!isNarrowSetupViewport()) {
    setupActionsMore.hidden = false;
    setupMoreToggle.setAttribute("aria-expanded", "true");
    return;
  }
  setupActionsMore.hidden = !open;
  setupMoreToggle.setAttribute("aria-expanded", open ? "true" : "false");
  setupMoreToggle.textContent = open ? "Less" : "More";
}

function bindSetupMoreTools() {
  if (!setupMoreToggle || !setupActionsMore) return;
  // Phones: collapsed by default so Settings/Start stay reachable
  setSetupMoreOpen(!isNarrowSetupViewport());
  setupMoreToggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const open = setupMoreToggle.getAttribute("aria-expanded") === "true";
    setSetupMoreOpen(!open);
  });
  window.addEventListener("resize", () => {
    if (!isNarrowSetupViewport()) setSetupMoreOpen(true);
    else if (setupMoreToggle.getAttribute("aria-expanded") !== "true") setSetupMoreOpen(false);
  });
}

function bindSetupNavExtras() {
  const nav = document.querySelector("#setupSteps");
  const toggle = document.querySelector("#setupNavToggle");
  const pinBtn = document.querySelector("#setupNavPin");
  const flyout = document.querySelector("#setupStepFlyout");
  if (!nav) return;

  const saved = localStorage.getItem("morkyn-setup-nav-mode");
  // Default: flyout (mobile-friendly). Pin only if user chose it and screen is wide.
  // On phones always force flyout so the form is usable.
  if (isNarrowSetupViewport()) applySetupNavMode("flyout");
  else applySetupNavMode(saved === "pin" ? "pin" : "flyout");

  toggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (nav.classList.contains("isPinned")) return;
    const open = toggle.getAttribute("aria-expanded") === "true";
    if (open) closeSetupStepFlyout();
    else openSetupStepFlyout();
  });

  pinBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (isNarrowSetupViewport()) {
      applySetupNavMode("flyout");
      return;
    }
    const next = nav.classList.contains("isPinned") ? "flyout" : "pin";
    applySetupNavMode(next);
  });

  // Close flyout when clicking outside
  document.addEventListener("click", (event) => {
    if (!nav.classList.contains("isFlyout") || !nav.classList.contains("isOpen")) return;
    if (nav.contains(event.target)) return;
    closeSetupStepFlyout();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSetupStepFlyout();
  });

  // Keep layout mode correct on resize (unpin if too narrow)
  window.addEventListener("resize", () => {
    if (isNarrowSetupViewport()) {
      applySetupNavMode("flyout");
      return;
    }
    const mode = localStorage.getItem("morkyn-setup-nav-mode") || "flyout";
    applySetupNavMode(mode === "pin" ? "pin" : "flyout");
  });

  // Selecting a step from the list
  flyout?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-setup-step]");
    if (!btn) return;
    setSetupStep(Number(btn.dataset.setupStep));
  });
}

function categoryForTab(tabId) {
  return TAB_CATEGORIES.find((c) => c.tabs.some((t) => t.id === tabId)) || TAB_CATEGORIES[0];
}

function buildIndexTabButtons(categoryId) {
  if (!indexTabs) return;
  const cat = TAB_CATEGORIES.find((c) => c.id === categoryId) || TAB_CATEGORIES[0];
  activeTabCategory = cat.id;
  indexTabs.innerHTML = cat.tabs
    .map((tab) => {
      const active = tab.id === activeTab ? "active" : "";
      return `
        <button data-tab="${escapeHtml(tab.id)}" class="${active}" type="button">
          ${escapeHtml(tab.label)}
          <span class="popHint" data-popout="${escapeHtml(tab.id)}" title="Float as collapsible window">⧉</span>
          <span class="popHint popWindow" data-popout-window="${escapeHtml(tab.id)}" title="New window">↗</span>
        </button>
      `;
    })
    .join("");
  document.querySelectorAll(".tabCategoryBtn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tabCategory === cat.id);
  });
  const catSelect = document.querySelector("#tabCategorySelect");
  if (catSelect) catSelect.value = cat.id;
  markPoppedTabs();
}

function setActiveTab(tabId, options = {}) {
  const renderers = TAB_RENDERERS();
  if (!renderers[tabId]) tabId = "player";
  activeTab = tabId;
  const cat = categoryForTab(tabId);
  if (cat.id !== activeTabCategory || options.rebuild) buildIndexTabButtons(cat.id);
  else if (indexTabs) {
    indexTabs.querySelectorAll("button[data-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === activeTab);
    });
  }
  renderIndex();
  if (activeTab === "bible") loadBible().catch((error) => (indexContent.innerHTML = paragraphs(error.message)));
  if (activeTab === "model") loadModelConfig().catch((error) => (indexContent.innerHTML = paragraphs(error.message)));
}

function applyTabNavMode(mode) {
  tabNavMode = mode === "menu" ? "menu" : "side";
  localStorage.setItem("morkyn-tab-nav-mode", tabNavMode);
  const pane = document.querySelector(".indexPaneCategorized");
  const toggle = document.querySelector("#tabNavModeToggle");
  pane?.classList.toggle("tabNavMenu", tabNavMode === "menu");
  pane?.classList.toggle("tabNavSide", tabNavMode !== "menu");
  if (toggle) toggle.textContent = tabNavMode === "menu" ? "Menu" : "Side";
}

function bindTabCategoryNav() {
  buildIndexTabButtons(categoryForTab(activeTab).id);
  applyTabNavMode(tabNavMode);
  document.querySelector("#tabCategoryList")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab-category]");
    if (!btn) return;
    const cat = TAB_CATEGORIES.find((c) => c.id === btn.dataset.tabCategory);
    if (!cat) return;
    const prefer = cat.tabs.some((t) => t.id === activeTab) ? activeTab : cat.tabs[0].id;
    setActiveTab(prefer, { rebuild: true });
  });
  document.querySelector("#tabCategorySelect")?.addEventListener("change", (event) => {
    const cat = TAB_CATEGORIES.find((c) => c.id === event.currentTarget.value);
    if (!cat) return;
    const prefer = cat.tabs.some((t) => t.id === activeTab) ? activeTab : cat.tabs[0].id;
    setActiveTab(prefer, { rebuild: true });
  });
  document.querySelector("#tabNavModeToggle")?.addEventListener("click", () => {
    applyTabNavMode(tabNavMode === "side" ? "menu" : "side");
  });
}

function setupDescription(name) {
  const info = SETTING_INFO[name];
  if (!info?.description) return null;
  const description = document.createElement("p");
  description.className = "settingDescription";
  description.textContent = info.description;
  return description;
}

function decorateSetupFields() {
  setupForm.querySelectorAll("label").forEach((label) => {
    if (label.closest("fieldset")) return;
    const field = label.querySelector("input[name], select[name], textarea[name]");
    const name = field?.name;
    if (!name || !SETTING_INFO[name] || label.querySelector(".settingDescription")) return;
    label.classList.add("settingField");
    const description = setupDescription(name);
    if (description) label.append(description);

    ensureSelectUtilityOptions(field);
    ensureSettingControls(label, name);
    const hasCustomOption = Array.from(field.options || []).some((option) => option.value === "custom");
    if (field.tagName !== "SELECT" || !hasCustomOption) return;
    label.classList.add("hasCustomInput");

    const custom = document.createElement("textarea");
    custom.className = "customSettingInput";
    custom.dataset.customInput = name;
    custom.rows = 2;
    custom.maxLength = SETTING_LIMITS[name] || 120;
    custom.placeholder = SETTING_INFO[name].customPlaceholder || `Write your own ${label.querySelector("span")?.textContent?.toLowerCase() || "setting"}.`;
    label.append(custom);
  });

  setupForm.querySelectorAll("fieldset").forEach((fieldset) => {
    const name = fieldset.querySelector("input[name]")?.name;
    if (!name || !SETTING_INFO[name] || fieldset.querySelector(".settingDescription")) return;
    fieldset.classList.add("settingField");
    const description = setupDescription(name);
    if (description) fieldset.append(description);
    ensureSettingControls(fieldset, name);
  });
  setupForm.querySelectorAll(".optionSet[data-list-setting]").forEach((fieldset) => {
    ensureListUtilityOptions(fieldset);
    ensureSettingControls(fieldset, fieldset.dataset.listSetting);
  });

  updateCustomControls();
}

function ensureSelectUtilityOptions(field) {
  if (field?.tagName !== "SELECT" || !field.name) return;
  const values = Array.from(field.options).map((option) => option.value);
  const customOption = Array.from(field.options).find((option) => option.value === "custom");
  if (!values.includes("random")) {
    const randomOption = new Option("Random", "random");
    field.add(randomOption, customOption || null);
  }
  if (!values.includes("custom")) field.append(new Option("Custom", "custom"));
}

function ensureListUtilityOptions(fieldset) {
  const name = fieldset.dataset.listSetting;
  if (!name) return;
  const inputs = Array.from(fieldset.querySelectorAll(`input[name="${name}"]`));
  const values = inputs.map((input) => input.value);
  const textarea = fieldset.querySelector(`[data-list-custom="${name}"]`);
  const customLabel = inputs.find((input) => input.value === "custom")?.closest("label") || textarea;
  if (!values.includes("random")) {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" name="${escapeHtml(name)}" value="random" /> Random`;
    fieldset.insertBefore(label, customLabel || textarea || null);
  }
  if (!values.includes("custom")) {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" name="${escapeHtml(name)}" value="custom" /> Custom`;
    fieldset.insertBefore(label, textarea || null);
  }
  const randomLabel = fieldset.querySelector(`input[name="${name}"][value="random"]`)?.closest("label");
  const currentCustomLabel = fieldset.querySelector(`input[name="${name}"][value="custom"]`)?.closest("label");
  if (randomLabel && currentCustomLabel && randomLabel.compareDocumentPosition(currentCustomLabel) & Node.DOCUMENT_POSITION_PRECEDING) {
    fieldset.insertBefore(randomLabel, currentCustomLabel);
  }
}

function ensureSettingControls(container, name) {
  if (!name || container.querySelector(`[data-setting-controls="${name}"]`)) return;
  const controls = document.createElement("div");
  controls.className = "settingControls";
  controls.dataset.settingControls = name;
  controls.innerHTML = `
    <button class="miniButton" data-randomize-field="${escapeHtml(name)}" type="button">Randomize</button>
    <label class="settingLock"><input type="checkbox" data-lock-setting="${escapeHtml(name)}" /> Lock</label>
  `;

  // Labels: put Randomize/Lock on the title row so free-text fields stay easy to roll one-by-one.
  if (container.matches("label")) {
    const title = Array.from(container.children).find((child) => child.tagName === "SPAN");
    if (title) {
      const header = document.createElement("div");
      header.className = "settingFieldHeader";
      title.replaceWith(header);
      header.append(title, controls);
      return;
    }
  }

  // Fieldsets: keep controls visible under the legend, before option rows when possible.
  if (container.matches("fieldset")) {
    const legend = container.querySelector(":scope > legend");
    if (legend) {
      legend.insertAdjacentElement("afterend", controls);
      return;
    }
  }

  container.append(controls);
}

function updateCustomControls() {
  setupForm.querySelectorAll("[data-custom-input]").forEach((custom) => {
    const name = custom.dataset.customInput;
    const select = setupForm.elements[name];
    const enabled = select?.value === "custom";
    custom.classList.toggle("open", enabled);
    custom.disabled = !enabled;
  });
  setupForm.querySelectorAll("[data-list-custom]").forEach((custom) => {
    const name = custom.dataset.listCustom;
    const enabled = Array.from(setupForm.querySelectorAll(`input[name="${name}"][value="custom"]`)).some((input) => input.checked);
    custom.classList.toggle("open", enabled);
    custom.disabled = !enabled;
  });
  updateSystemStyleDescription();
  updateGainControls();
}

function updateGainControls() {
  setupForm.querySelectorAll("[data-custom-gain]").forEach((toggle) => {
    const name = toggle.dataset.customGain;
    const enabled = toggle.checked;
    const slider = setupForm.querySelector(`[data-gain-slider="${name}"]`);
    const note = setupForm.querySelector(`[data-gain-note="${name}"]`);
    const number = setupForm.querySelector(`[data-gain-number="${name}"]`);
    if (slider) {
      slider.disabled = !enabled;
    }
    if (number) {
      number.disabled = !enabled;
    }
    if (note) note.disabled = !enabled;
  });
  updateTextOptimizeControls();
}

function updateAbilityOriginControls() {
  const origin = abilityOrigin();
  const noneSelected = origin === "none";
  abilityOptions?.classList.toggle("abilitiesNone", noneSelected);
  if (noneSelected && abilityList.children.length) abilityList.innerHTML = "";
  const locked = noneSelected || setupRandomizationLocked();
  if (randomAbilityButton) randomAbilityButton.disabled = locked;
  if (addAbilityButton) addAbilityButton.disabled = locked;
  if (lockAbilityCount) lockAbilityCount.disabled = locked;
  setupForm.querySelectorAll('[data-lock-setting="special_abilities"]').forEach((input) => {
    input.disabled = locked;
  });
  abilityList.querySelectorAll("input, select, textarea, button").forEach((control) => {
    control.disabled = setupRandomizationLocked();
  });
  updateTextOptimizeControls();
}

function readSetupValue(formData, name) {
  const custom = readCustomText(name);
  if (custom) return custom;
  const value = formData.get(name) ?? setupForm.elements[name]?.value;
  if (value === "random") {
    const options = availableSelectValues(name);
    if (options.length) return choice(options);
    if (RANDOM_SETUP[name]?.length) return choice(RANDOM_SETUP[name]);
  }
  return value;
}

function readCustomText(name) {
  const select = setupForm.elements[name];
  const custom = setupForm.querySelector(`[data-custom-input="${name}"]`);
  if (select?.value !== "custom" || !custom?.value.trim()) return "";
  return custom.value.trim();
}

function readListSetting(formData, name, fallback) {
  const values = formData.getAll(name).map((value) => String(value || "").trim()).filter(Boolean);
  const custom = setupForm.querySelector(`[data-list-custom="${name}"]`)?.value.trim();
  const finalValues = values.filter((value) => value !== "custom" && value !== "random");
  if (values.includes("random")) finalValues.push(...randomListSelection(name));
  if (values.includes("custom") && custom) finalValues.push(custom);
  const uniqueValues = [];
  const seenValues = new Set();
  for (const value of finalValues.join(",").split(",")) {
    const cleanValue = value.trim();
    const key = cleanValue.toLowerCase();
    if (!cleanValue || seenValues.has(key)) continue;
    seenValues.add(key);
    uniqueValues.push(cleanValue);
  }
  return (uniqueValues.length ? uniqueValues.join(", ") : fallback).slice(0, SETTING_LIMITS[name] || 120);
}

function readGainSetting(name) {
  const custom = setupForm.querySelector(`[data-custom-gain="${name}"]`)?.checked;
  const slider = setupForm.querySelector(`[data-gain-slider="${name}"]`);
  const number = setupForm.querySelector(`[data-gain-number="${name}"]`);
  const note = setupForm.querySelector(`[data-gain-note="${name}"]`);
  const multiplier = Math.max(0, Math.min(100, finiteNumber(number?.value || slider?.value || 1, 1)));
  return {
    speed: setupValueText(new FormData(setupForm), name, "normal", SETTING_LIMITS[name] || 80),
    multiplier: custom ? multiplier : null,
    note: custom ? String(note?.value || "").trim() : "",
  };
}

function abilityTemplate(ability = {}) {
  const id = globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : String(Date.now() + Math.random());
  const locked = ability.locked ?? abilityDefaultLocked();
  const growthMath =
    ability.growth_math ||
    (ability.compounding || ability.one_skill ? choice(GROWTH_MATH_SAMPLES) : "");
  return `
    <article class="abilitySetupCard" data-ability-id="${escapeHtml(id)}">
      <div class="abilityCardHeader">
        <label>
          <span>Name</span>
          <input data-ability-field="name" value="${escapeHtml(ability.name || "")}" placeholder="Echo Step" maxlength="100" />
        </label>
        <fieldset class="toggleSet compactToggle">
          <legend>State</legend>
          <label><input type="radio" data-ability-field="locked" name="ability_locked_${escapeHtml(id)}" value="false" ${locked ? "" : "checked"} /> Unlocked</label>
          <label><input type="radio" data-ability-field="locked" name="ability_locked_${escapeHtml(id)}" value="true" ${locked ? "checked" : ""} /> Locked</label>
        </fieldset>
      </div>
      <label>
        <span>Base Description</span>
        <textarea data-ability-field="description" rows="2" maxlength="800" placeholder="What this ability does. The model cannot rewrite this after setup.">${escapeHtml(ability.description || "")}</textarea>
      </label>
      <div class="abilityCardGrid">
        <label>
          <span>Prerequisites</span>
          <textarea data-ability-field="prerequisites" rows="2" maxlength="500" placeholder="Optional: unlock condition, training, item, oath, event.">${escapeHtml(ability.prerequisites || "")}</textarea>
        </label>
        <label>
          <span>Cost</span>
          <select data-ability-field="cost_mode">
            <option value="no cost" ${!ability.cost || ability.cost === "no cost" ? "selected" : ""}>No cost</option>
            <option value="model decides" ${ability.cost === "model decides" ? "selected" : ""}>Let model decide</option>
            <option value="custom" ${ability.cost && !["no cost", "model decides"].includes(ability.cost) ? "selected" : ""}>Custom cost</option>
          </select>
          <textarea data-ability-field="cost" rows="2" maxlength="300" placeholder="Optional custom cost, limit, cooldown, resource, injury, debt, etc.">${escapeHtml(ability.cost && !["no cost", "model decides"].includes(ability.cost) ? ability.cost : "")}</textarea>
        </label>
      </div>
      <label class="wide">
        <span>Growth Math</span>
        <textarea data-ability-field="growth_math" rows="3" maxlength="800" placeholder="How this power grows in numbers: XP_to_next, rank thresholds, per-use XP × risk, soft caps, rank→bonus. Example: F0 E80 D200; use 5-12 XP × risk (1/2/3); +1 check per rank.">${escapeHtml(growthMath)}</textarea>
      </label>
      <div class="abilityCardActions">
        <button class="secondaryButton randomizeOneAbility" type="button">Randomize This</button>
        <button class="secondaryButton addAbilityAfter" type="button">Add Ability Below</button>
        <button class="secondaryButton removeAbility" type="button">Remove</button>
      </div>
    </article>
  `;
}

function addAbility(ability = {}) {
  if (abilityOrigin() === "none") setAbilityOrigin("acquired");
  abilityList.insertAdjacentHTML("beforeend", abilityTemplate(ability));
  ensureTextAiControls(abilityList.lastElementChild || abilityList);
  decorateFunctionHelp(abilityList.lastElementChild || abilityList);
  updateAbilityOriginControls();
}

function abilityFingerprint(ability) {
  if (!ability || typeof ability !== "object") return "";
  return `${String(ability.name || "").trim().toLowerCase()}||${String(ability.description || "").trim().toLowerCase()}`;
}

function randomAbilityPreset(avoidList = []) {
  const avoid = new Set(
    (Array.isArray(avoidList) ? avoidList : [])
      .map((a) => abilityFingerprint(a))
      .filter(Boolean),
  );
  const pool = ABILITY_PRESETS.filter((p) => !avoid.has(abilityFingerprint(p)));
  const pick = pool.length ? choice(pool) : choice(ABILITY_PRESETS);
  return { ...pick };
}

function randomizeAbility() {
  addAbility(randomAbilityPreset());
}

function collectAbilities() {
  if (abilityOrigin() === "none") return [];
  return Array.from(abilityList.querySelectorAll(".abilitySetupCard"))
    .map((card) => {
      const field = (name) => card.querySelector(`[data-ability-field="${name}"]`);
      const name = field("name")?.value.trim() || "";
      const description = field("description")?.value.trim() || "";
      const locked = card.querySelector('[data-ability-field="locked"]:checked')?.value === "true";
      const prerequisites = field("prerequisites")?.value.trim() || "";
      const costMode = field("cost_mode")?.value || "no cost";
      const cost = costMode === "custom" ? field("cost")?.value.trim() || "model decides" : costMode;
      const growth_math = field("growth_math")?.value.trim() || "";
      return { name, description, locked, prerequisites, cost, growth_math };
    })
    .filter((ability) => ability.name || ability.description);
}

function updateSystemStyleDescription() {
  const description = document.querySelector("#systemStyleDescription");
  const value = setupForm.elements.system_style?.value;
  if (description) description.textContent = SYSTEM_STYLE_DESCRIPTIONS[value] || "";
}

async function refreshContinueButton() {
  const cont = document.querySelector("#menuContinue");
  const status = document.querySelector("#mainMenuStatus");
  if (!cont) return null;
  try {
    const res = await fetch("/api/playthrough/continue", { cache: "no-store" });
    const info = await res.json().catch(() => ({}));
    const ok = Boolean(info.ok);
    cont.hidden = false;
    cont.disabled = !ok;
    cont.classList.toggle("mainMenuDisabled", !ok);
    cont.setAttribute("aria-disabled", ok ? "false" : "true");
    cont.title = ok
      ? `Continue ${info.player_name || "run"} @ ${info.location || "?"} (turn ${info.turn ?? "?"})`
      : "No previous playthrough found";
    if (status) {
      status.textContent = ok
        ? `Continue available: ${info.player_name || "player"} · ${info.location || "somewhere"} · turn ${info.turn ?? 0}${info.source === "slot" ? " (autosave)" : ""}`
        : "Ready. Start a new game or load a save.";
    }
    return info;
  } catch (error) {
    cont.disabled = true;
    cont.hidden = false;
    cont.classList.add("mainMenuDisabled");
    if (status) status.textContent = "Could not check for a previous game.";
    return null;
  }
}

function showMainMenu() {
  mainMenuView?.classList.remove("hidden");
  setupView?.classList.add("hidden");
  gameView?.classList.add("hidden");
  refreshContinueButton();
}

function showGameView() {
  mainMenuView?.classList.add("hidden");
  setupView?.classList.add("hidden");
  gameView?.classList.remove("hidden");
  // Ensure play chrome paints even if we only unhide the view.
  if (state?.setup_complete || state?.player) {
    const location = state.current_location || {};
    const shortName = location.name || "Unknown";
    const code = location.code || "";
    if (locationLine) {
      locationLine.textContent = code ? `${code} · ${shortName}` : shortName;
      locationLine.title = String(location.summary || shortName);
    }
    applyPlayLayout();
    renderHistory();
    renderIndex();
    updateTravelStatus(state.travel_ready);
    refreshLocalMap();
    refreshNpcStage();
    restoreSavedFloatWindows();
  }
}

/** Newest-first history entry matching one of the given kinds. */
function lastHistoryEntry(kinds) {
  const history = Array.isArray(state?.history) ? state.history : [];
  if (!kinds || !kinds.length) return history[0] || null;
  const want = new Set(kinds.map((k) => String(k).toLowerCase()));
  return history.find((entry) => want.has(String(entry?.kind || "").toLowerCase())) || null;
}

/**
 * Rehydrate scene panels after Continue / load slot.
 * Server `resume` (if present) is preferred; otherwise dig journal history.
 */
function restoreLastTurnPanels(resume = null) {
  const snap = resume && typeof resume === "object" ? resume : {};
  const narrationText =
    String(snap.last_narration || "").trim() ||
    String(lastHistoryEntry(["narration"])?.content || "").trim() ||
    String(snap.last_summary || "").trim() ||
    String((state?.turn_summaries || [])[0]?.summary || "").trim();
  const inputEntry = lastHistoryEntry(["player", "opening", "continue", "regenerate"]);
  const inputText =
    String(snap.last_input || "").trim() ||
    String(inputEntry?.content || "").trim();
  const inputKind = String(snap.last_input_kind || inputEntry?.kind || "").trim();

  if (latestInput) {
    if (inputText) {
      const label =
        inputKind === "opening"
          ? "Opening"
          : inputKind === "continue"
            ? "Continue"
            : inputKind === "regenerate"
              ? "Regenerate"
              : "Last input";
      latestInput.innerHTML = paragraphs(inputKind && inputKind !== "player" ? `[${label}] ${inputText}` : inputText);
    } else {
      latestInput.innerHTML = paragraphs("(resumed from save)");
    }
  }

  if (latestOutput) {
    if (narrationText) {
      latestOutput.innerHTML = `<article class="turnNarration">${paragraphs(narrationText)}</article>`;
    } else {
      latestOutput.innerHTML = paragraphs("Continued from last save. What do you do?");
    }
  }

  // Force history list even if renderShell ran before state was fully assigned.
  renderHistory();
  if (historyEl && !(state?.history || []).length) {
    historyEl.innerHTML = `<p class="empty">No journal entries in this save yet.</p>`;
  }
}

/**
 * Enter the play view from a loaded save/continue response and fully paint UI.
 */
async function enterPlayFromSave(nextState, options = {}) {
  state = nextState || state;
  if (!state) throw new Error("No playthrough state to enter.");
  if (!state.setup_complete && state.player) state.setup_complete = true;
  if (!state.setup_complete) throw new Error("Save loaded but is not a complete playthrough.");

  // Always force into game view (do not bounce back to main menu).
  mainMenuView?.classList.add("hidden");
  setupView?.classList.add("hidden");
  gameView?.classList.remove("hidden");

  renderShell(state, { forceGame: true });
  restoreLastTurnPanels(options.resume || null);

  // Continue/load: narration is the main screen unless the player locked a custom layout.
  applyPlayLayout();
  setSceneFocus(true, { scroll: true, focusInput: true, smooth: false });

  // Map paint needs the game view visible for layout; refresh once more after frame.
  await refreshLocalMap();
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  await refreshLocalMap();

  const meta = document.querySelector("#playMapMeta");
  if (meta && /no map yet/i.test(meta.textContent || "")) {
    // One more try after a tick — tile endpoint may warm on first hit.
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    await refreshLocalMap();
  }

  // After map paint, keep scene column primary and ensure narration is in view.
  setSceneFocus(true, { scroll: true, focusInput: true, smooth: true });
}

async function continuePlaythrough() {
  const status = document.querySelector("#mainMenuStatus");
  const cont = document.querySelector("#menuContinue");
  if (cont?.disabled) return;
  if (status) status.textContent = "Loading last playthrough…";
  try {
    const res = await fetch("/api/playthrough/continue", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    const nextState = data.state || (await (await fetch("/api/state")).json());
    await enterPlayFromSave(nextState, { resume: data.resume || null });
    if (status) {
      const hist = data.resume?.history_count ?? (nextState.history || []).length;
      const mapNote = data.resume?.has_map === false ? " · map missing from save" : "";
      status.textContent = `Loaded (${hist} journal entries)${mapNote}.`;
    }
  } catch (error) {
    if (status) status.textContent = error.message || String(error);
    await refreshContinueButton();
  }
}

const SETUP_TUTORIAL_KEY = "morkyn-setup-tutorial-v8";
let setupTourIndex = -1;
let setupTourActive = false;
let setupTourKeepFlyoutOpen = false;
let setupTourResizeBound = false;

function hasSeenSetupTutorial() {
  try {
    return localStorage.getItem(SETUP_TUTORIAL_KEY) === "1";
  } catch {
    return false;
  }
}

function markSetupTutorialSeen() {
  try {
    localStorage.setItem(SETUP_TUTORIAL_KEY, "1");
  } catch {
    /* ignore */
  }
}

function fieldControl(name, kind) {
  if (kind === "input") return setupForm?.querySelector(`[name="${name}"]`);
  if (kind === "randomize") return setupForm?.querySelector(`[data-setting-controls="${name}"] [data-randomize-field="${name}"]`);
  if (kind === "lock") {
    const input = setupForm?.querySelector(`[data-lock-setting="${name}"]`);
    return input?.closest("label") || input;
  }
  if (kind === "ai") {
    const field = setupForm?.querySelector(`[name="${name}"]`);
    return field?.closest(".textAiField, .settingField, label")?.querySelector("[data-text-ai-open]") || null;
  }
  return null;
}

/**
 * Guided tour: keep enough stops for clarity, with full context in each tip.
 * (User feedback: short compacted text was hard to follow — not that there were too many stops.)
 */
function getSetupTourSteps() {
  const openMenu = () => {
    applySetupNavMode("flyout");
    setupTourKeepFlyoutOpen = true;
    openSetupStepFlyout();
  };
  return [
    {
      id: "steps-chip",
      title: "Setup pages",
      text:
        "This control opens your setup pages. Setup is split into short sections so you never face one endless form. " +
        "Tap it anytime to jump: Identity, Powers, World, People, Rules, and Checks. " +
        "On phones it drops down over the form so the page stays full-width.",
      shape: "pill",
      select: () => document.querySelector("#setupNavToggle"),
      before: () => {
        applySetupNavMode("flyout");
        setupTourKeepFlyoutOpen = false;
        closeSetupStepFlyout();
      },
    },
    {
      id: "llm",
      title: "LLM Settings",
      text:
        "This is where you connect the brain of the game — a local GGUF, xAI/Grok, or another OpenAI-compatible API. " +
        "Randomize, AI field fill, suggestions, and in-game turns all use this connection. " +
        "If something AI-related fails, check here first.",
      shape: "pill",
      select: () => document.querySelector("#setupModelButton"),
    },
    {
      id: "save",
      title: "Save Settings",
      text:
        "Saves your current setup choices as a JSON file on this machine (not the cloud). " +
        "Use it when you’ve tuned a world you like and want to reuse it later via Load Settings. " +
        "It stores setup options — not a mid-play save slot (those are under Load / Save in the main menu).",
      shape: "pill",
      select: () => document.querySelector("#saveSetupSettings"),
    },
    {
      id: "randomize-all",
      title: "Randomize (whole setup)",
      text:
        "Fills every unlocked field in a sensible order (character → world → people → rules). " +
        "Optional idea box next to it steers the overall concept (tone, genre, hook). " +
        "Safe to spam: it won’t touch fields you’ve Locked.",
      shape: "rect",
      select: () => document.querySelector(".setupRandomizeAll") || document.querySelector("#randomizeSetup"),
    },
    {
      id: "menu-open",
      title: "Step menu",
      text:
        "Here’s the full page list, grouped so it’s easier to scan:\n" +
        "• You — Identity (who you are) and Powers (optional abilities)\n" +
        "• Setting — World (genre, map, magic) and People (NPCs, factions)\n" +
        "• System — Rules (difficulty, death, loot) and Checks (dice)\n" +
        "Next we’ll point at each page name once so the map sticks.",
      shape: "rect",
      select: () => document.querySelector("#setupStepFlyout") || document.querySelector("#setupStepGroups"),
      before: openMenu,
    },
    {
      id: "step-0",
      title: "Identity",
      text:
        "Who you are on paper: name, titles, age, sex, backstory mode, and memory rules. " +
        "This is what the model treats as the hero’s baseline. " +
        "You don’t need a novel — even a short name and tone already steer the opening scene.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="0"]'),
      before: openMenu,
    },
    {
      id: "step-1",
      title: "Powers",
      text:
        "Optional starting abilities (none is fine). " +
        "Base ability text is locked once play begins so the model can’t quietly rewrite what you defined. " +
        "Skip this page if you want a grounded, low-magic start.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="1"]'),
      before: openMenu,
    },
    {
      id: "step-2",
      title: "World",
      text:
        "Genre, map, start location, tone, magic, races, and economy. " +
        "This is the stage the model improvises inside — change it and the whole story’s texture changes. " +
        "Generate a map here if you want travel and terrain later.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="2"]'),
      before: openMenu,
    },
    {
      id: "step-3",
      title: "People",
      text:
        "How crowded and political the social world is: NPC density, factions, ranks, and quest style. " +
        "Sparse worlds feel lonely and hard; dense worlds throw names and plots at you faster. " +
        "Pick what kind of social pressure you want the model to keep up.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="3"]'),
      before: openMenu,
    },
    {
      id: "step-4",
      title: "Rules",
      text:
        "Risk and progression: difficulty, death, loot, inventory limits, skills, and whether an in-world “system” UI appears. " +
        "These are the guardrails the model should respect when it narrates outcomes. " +
        "If combat or failure feels wrong later, this page is usually why.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="4"]'),
      before: openMenu,
    },
    {
      id: "step-5",
      title: "Checks",
      text:
        "Optional dice for speech, strength, lore, and encounters. " +
        "When on, the game can roll openly so success isn’t pure fiat. " +
        "Turn them off if you want pure narrative; leave them on if you like fair risk.",
      shape: "pill",
      select: () => document.querySelector('[data-setup-step="5"]'),
      before: openMenu,
    },
    {
      id: "name-field",
      title: "A normal field",
      text:
        "Every page is made of fields like this. Type whatever you want — nothing is required beyond a name. " +
        "We’ll stay on Identity for the next few tips so the screen doesn’t jump. " +
        "The same Randomize / Lock / AI controls appear on most free-text and choice fields.",
      shape: "rect",
      select: () => fieldControl("player_name", "input")?.closest("label") || fieldControl("player_name", "input"),
      before: () => {
        setupTourKeepFlyoutOpen = false;
        closeSetupStepFlyout();
        setSetupStep(0);
      },
    },
    {
      id: "name-random",
      title: "Field Randomize",
      text:
        "Rolls only this one setting, using the rest of your setup as context (so a title can match a grim world, etc.). " +
        "Different from the big top-bar Randomize, which walks the whole form. " +
        "Use this when one line feels blank but you like everything else.",
      shape: "pill",
      select: () => fieldControl("player_name", "randomize"),
      before: () => setSetupStep(0),
    },
    {
      id: "name-lock",
      title: "Lock",
      text:
        "When locked, full Randomize and bulk rolls skip this field so your choice stays put. " +
        "Unlock anytime. " +
        "Handy after you get a name or rule you love and still want to re-roll the rest of the world.",
      shape: "pill",
      select: () => fieldControl("player_name", "lock"),
      before: () => setSetupStep(0),
    },
    {
      id: "name-ai",
      title: "AI fill",
      text:
        "Opens a small prompt box so the model can write this field for you (needs a working LLM under Settings). " +
        "You can ask for a name, a backstory beat, or custom world rules. " +
        "Optional — typing by hand always works; AI is just a helper when you want a draft.",
      shape: "pill",
      select: () => fieldControl("player_name", "ai"),
      before: () => setSetupStep(0),
    },
    {
      id: "art-card",
      title: "Character art (optional)",
      text:
        "Optional local pictures for your hero. Expand this card to see the tools.\n" +
        "• Set or install ForgeSD — connect your image server first\n" +
        "• Face / Body frames — the actual images\n" +
        "• Generate — paint from hair / face / clothing fields\n" +
        "• Studio & Image Library — only unlock after Forge is online (browse/pick gens)\n" +
        "If you already know image tools, you only need the labels — not a full tutorial.",
      shape: "rect",
      select: () => document.querySelector("#characterPortraitCard") || document.querySelector("#setupArtCollapseBtn"),
      before: () => {
        setupTourKeepFlyoutOpen = false;
        closeSetupStepFlyout();
        setSetupStep(0);
        applySetupArtCollapsed(false, { persist: false });
        showSetupArtGuide({ force: true });
      },
    },
    {
      id: "art-forge",
      title: "ForgeSD first",
      text:
        "This button opens image settings (path, install Forge extensions, Test Connection).\n" +
        "Studio and Image Library stay hidden until that connection succeeds — so nothing looks “broken” offline.\n" +
        "You can still drop PNGs onto the frames without Forge.",
      shape: "pill",
      select: () => document.querySelector("#setupArtOpenImageSettings"),
      before: () => {
        setSetupStep(0);
        applySetupArtCollapsed(false, { persist: false });
      },
    },
    {
      id: "start",
      title: "Start when ready",
      text:
        "Press Start to begin play with these choices. " +
        "They aren’t decoration — genre, death rules, NPCs, and checks shape how the model runs your world. " +
        "You can still Randomize earlier pages or Load a saved setup later if you want a different tone.",
      shape: "pill",
      select: () => document.querySelector("#setupStart"),
      before: () => {
        setupTourKeepFlyoutOpen = false;
        closeSetupStepFlyout();
      },
    },
  ];
}

function openSetupTutorial() {
  const el = document.querySelector("#setupTutorial");
  if (!el) return;
  el.classList.remove("hidden");
  el.classList.remove("isTouring");
  document.querySelector("#setupTutorialIntro")?.classList.remove("hidden");
  document.querySelector("#setupTourLayer")?.classList.add("hidden");
  setupTourActive = false;
  setupTourIndex = -1;
  document.querySelector("#setupTutorialContinue")?.focus();
}

function endSetupTour(remember = true) {
  setupTourActive = false;
  setupTourKeepFlyoutOpen = false;
  setupTourIndex = -1;
  document.querySelector("#setupTourLayer")?.classList.add("hidden");
  document.querySelector("#setupTutorial")?.classList.add("hidden");
  document.querySelector("#setupTutorial")?.classList.remove("isTouring");
  document.querySelector("#setupTutorialIntro")?.classList.remove("hidden");
  clearSetupTourHighlight();
  closeSetupStepFlyout();
  const dontShow = document.querySelector("#setupTutorialDontShow");
  // Only remember dismissal when "Don't show again" is checked (default).
  if (remember && dontShow?.checked) markSetupTutorialSeen();
}

function clearSetupTourHighlight() {
  document.querySelectorAll(".setupTourTarget").forEach((el) => el.classList.remove("setupTourTarget"));
}

function positionSetupTour(target, options = {}) {
  const hole = document.querySelector("#setupTourHole");
  const arrow = document.querySelector("#setupTourArrow");
  const tip = document.querySelector("#setupTourTip");
  if (!hole || !arrow || !tip || !target) return;

  const rect = target.getBoundingClientRect();
  const shape = options.shape || "circle";
  const padX = shape === "rect" || shape === "pill" ? 10 : 14;
  const padY = shape === "rect" || shape === "pill" ? 8 : 14;
  const w = Math.max(40, rect.width + padX * 2);
  const h = Math.max(40, rect.height + padY * 2);
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 12;
  const gap = 10;
  const arrowW = 40;
  const arrowH = 56;

  // Spotlight on the control
  hole.style.width = `${w}px`;
  hole.style.height = `${h}px`;
  hole.style.left = `${cx - w / 2}px`;
  hole.style.top = `${cy - h / 2}px`;
  hole.style.borderRadius = shape === "rect" ? "12px" : shape === "pill" ? "999px" : "50%";

  // Measure tip (follow target — not docked at bottom)
  tip.classList.remove("isDocked");
  tip.style.bottom = "auto";
  tip.style.transform = "none";
  tip.style.visibility = "hidden";
  tip.classList.remove("hidden");
  // Force layout so we get real size for placement
  const tipRect = tip.getBoundingClientRect();
  const tipW = Math.min(tipRect.width || 420, vw - margin * 2);
  const tipH = tipRect.height || 200;

  const spaceBelow = vh - rect.bottom - margin;
  const spaceAbove = rect.top - margin;
  const needBelow = tipH + arrowH + gap * 2;
  const needAbove = tipH + arrowH + gap * 2;

  // Prefer: tip under highlight (arrow between, pointing up at control)
  // Else: tip above (arrow pointing down)
  // Else: tip to the side of the highlight
  let place = "below";
  if (spaceBelow >= needBelow) place = "below";
  else if (spaceAbove >= needAbove) place = "above";
  else if (vw - rect.right - margin >= tipW + gap) place = "right";
  else if (rect.left - margin >= tipW + gap) place = "left";
  else place = spaceBelow >= spaceAbove ? "below" : "above";

  let tipLeft = cx - tipW / 2;
  let tipTop = 0;
  let arrowLeft = cx - arrowW / 2;
  let arrowTop = 0;

  if (place === "below") {
    // [highlight] → arrow (point up) → tip card
    arrow.classList.add("isBelow");
    arrow.classList.remove("isAbove");
    arrowTop = rect.bottom + gap;
    tipTop = arrowTop + arrowH + gap;
    if (tipTop + tipH > vh - margin) tipTop = Math.max(margin, vh - margin - tipH);
  } else if (place === "above") {
    // tip card → arrow (point down) → [highlight]
    arrow.classList.add("isAbove");
    arrow.classList.remove("isBelow");
    tipTop = rect.top - gap - arrowH - gap - tipH;
    if (tipTop < margin) tipTop = margin;
    arrowTop = tipTop + tipH + gap;
    // Keep arrow just above the control if clamp pushed tip
    if (arrowTop + arrowH > rect.top - 4) arrowTop = Math.max(margin, rect.top - arrowH - gap);
  } else if (place === "right") {
    arrow.classList.add("isAbove");
    arrow.classList.remove("isBelow");
    tipLeft = rect.right + gap + arrowW;
    tipTop = Math.max(margin, Math.min(cy - tipH / 2, vh - margin - tipH));
    arrowLeft = rect.right + gap;
    arrowTop = Math.max(margin, cy - arrowH / 2);
  } else {
    // left
    arrow.classList.add("isAbove");
    arrow.classList.remove("isBelow");
    tipLeft = rect.left - gap - arrowW - tipW;
    tipTop = Math.max(margin, Math.min(cy - tipH / 2, vh - margin - tipH));
    arrowLeft = rect.left - gap - arrowW;
    arrowTop = Math.max(margin, cy - arrowH / 2);
  }

  tipLeft = Math.max(margin, Math.min(tipLeft, vw - margin - tipW));
  arrowLeft = Math.max(margin, Math.min(arrowLeft, vw - margin - arrowW));
  arrowTop = Math.max(margin, Math.min(arrowTop, vh - margin - arrowH));

  // Prefer aligning tip under the control center when above/below
  if (place === "below" || place === "above") {
    tipLeft = Math.max(margin, Math.min(cx - tipW / 2, vw - margin - tipW));
  }

  tip.style.left = `${tipLeft}px`;
  tip.style.top = `${tipTop}px`;
  tip.style.visibility = "visible";

  arrow.style.left = `${arrowLeft}px`;
  arrow.style.top = `${arrowTop}px`;

  target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
}

async function showSetupTourStep(index) {
  const steps = getSetupTourSteps();
  if (index < 0 || index >= steps.length) {
    endSetupTour(true);
    return;
  }
  setupTourActive = true;
  setupTourIndex = index;
  const step = steps[index];

  document.querySelector("#setupTutorial")?.classList.add("isTouring");
  document.querySelector("#setupTutorialIntro")?.classList.add("hidden");
  document.querySelector("#setupTourLayer")?.classList.remove("hidden");

  try {
    await step.before?.();
  } catch (_) {
    /* ignore */
  }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

  clearSetupTourHighlight();
  let target = step.select?.();
  if (!target || (target.offsetParent === null && getComputedStyle(target).display === "none")) {
    await new Promise((r) => setTimeout(r, 50));
    target = step.select?.();
  }
  if (!target) {
    showSetupTourStep(index + 1);
    return;
  }

  target.classList.add("setupTourTarget");
  const meta = document.querySelector("#setupTourStepMeta");
  const title = document.querySelector("#setupTourTipTitle");
  const text = document.querySelector("#setupTourTipText");
  const nextBtn = document.querySelector("#setupTourNext");
  const backBtn = document.querySelector("#setupTourBack");
  if (meta) meta.textContent = `Step ${index + 1} of ${steps.length}`;
  if (title) title.textContent = step.title || `Step ${index + 1}`;
  if (text) {
    // Preserve intentional line breaks as separate lines for multi-line context tips
    text.textContent = "";
    const parts = String(step.text || "").split("\n").filter((line) => line.length);
    parts.forEach((line, i) => {
      if (i) text.appendChild(document.createElement("br"));
      text.appendChild(document.createTextNode(line));
    });
  }
  if (nextBtn) nextBtn.textContent = index >= steps.length - 1 ? "Finish" : "Next";
  if (backBtn) backBtn.disabled = index <= 0;

  positionSetupTour(target, { shape: step.shape || "circle" });
  window.setTimeout(() => positionSetupTour(target, { shape: step.shape || "circle" }), 320);
}

function startSetupTour() {
  document.querySelector("#setupTutorialIntro")?.classList.add("hidden");
  showSetupTourStep(0);
}

function advanceSetupTour() {
  const steps = getSetupTourSteps();
  if (setupTourIndex >= steps.length - 1) {
    endSetupTour(true);
    return;
  }
  showSetupTourStep(setupTourIndex + 1);
}

function retreatSetupTour() {
  if (setupTourIndex <= 0) return;
  showSetupTourStep(setupTourIndex - 1);
}

function bindSetupTutorialOnce() {
  if (bindSetupTutorialOnce.bound) return;
  bindSetupTutorialOnce.bound = true;
  document.querySelector("#setupTutorialContinue")?.addEventListener("click", () => startSetupTour());
  document.querySelector("#setupTourNext")?.addEventListener("click", () => advanceSetupTour());
  document.querySelector("#setupTourBack")?.addEventListener("click", () => retreatSetupTour());
  document.querySelector("#setupTourSkip")?.addEventListener("click", () => endSetupTour(true));
  document.addEventListener("keydown", (event) => {
    const root = document.querySelector("#setupTutorial");
    if (!root || root.classList.contains("hidden")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      endSetupTour(true);
    } else if (event.key === "Enter" && setupTourActive) {
      event.preventDefault();
      advanceSetupTour();
    } else if (event.key === "ArrowLeft" && setupTourActive) {
      event.preventDefault();
      retreatSetupTour();
    } else if (event.key === "ArrowRight" && setupTourActive) {
      event.preventDefault();
      advanceSetupTour();
    }
  });
  if (!setupTourResizeBound) {
    setupTourResizeBound = true;
    window.addEventListener("resize", () => {
      if (!setupTourActive) return;
      const target = document.querySelector(".setupTourTarget");
      const steps = getSetupTourSteps();
      const step = steps[setupTourIndex];
      if (target) positionSetupTour(target, { shape: step?.shape || "circle" });
    });
  }
}

function showSetupWizard(options = {}) {
  mainMenuView?.classList.add("hidden");
  setupView?.classList.remove("hidden");
  gameView?.classList.add("hidden");
  setSetupStep(0);
  updateConditionalSetup();
  bindSetupTutorialOnce();
  // New game: character art always starts collapsed (user can expand anytime).
  loadImageConfig()
    .catch(() => {})
    .finally(() => {
      initSetupArtCollapse({ forceCollapsed: true });
    });
  // First-time (or forced) tour
  if (options.forceTutorial || !hasSeenSetupTutorial()) {
    openSetupTutorial();
  } else {
    endSetupTour(false);
  }
}

function renderShell(nextState, options = {}) {
  state = nextState;
  const ready = Boolean(state.setup_complete) || (options.forceGame && Boolean(state?.player));
  // Prefer server-cached portrait when present
  if (state.player_portrait?.data_url) {
    try {
      localStorage.setItem("morkyn-player-portrait", state.player_portrait.data_url);
    } catch (_) {
      /* ignore quota */
    }
  }
  if (!ready) {
    // Prefer main menu over dumping into setup immediately.
    if (!options.forceGame) showMainMenu();
    return;
  }
  if (options.forceGame && !state.setup_complete && state.player) {
    state.setup_complete = true;
  }

  showGameView();

  const location = state.current_location || {};
  // Short location line only — long summaries destroy the top bar layout.
  const shortName = location.name || "Unknown";
  const code = location.code || "";
  if (locationLine) {
    locationLine.textContent = code ? `${code} · ${shortName}` : shortName;
    locationLine.title = String(location.summary || shortName);
  }
  renderHistory();
  renderIndex();
  updateTravelStatus(state.travel_ready);
  refreshLocalMap();
  refreshNpcStage();
  pushAllPopouts();
  queueAutoNpcPortraits();
}

function clearSuggestions(options = {}) {
  if (suggestionsEl) suggestionsEl.innerHTML = "";
  suggestionPanel?.classList.add("hidden");
  if (!options.keepInstruction && suggestionInstruction) suggestionInstruction.value = "";
}

function renderSuggestions(suggestions) {
  if (!suggestionsEl || !suggestionPanel) return;
  const items = Array.isArray(suggestions) ? suggestions.filter(Boolean).slice(0, 3) : [];
  suggestionsEl.innerHTML = items
    .map(
      (suggestion) => `
        <article class="suggestionItem">
          <p>${escapeHtml(suggestion)}</p>
          <button class="useSuggestionButton" data-suggestion="${escapeHtml(suggestion)}" type="button">use</button>
        </article>
      `,
    )
    .join("");
  suggestionPanel.classList.toggle("hidden", items.length === 0);
  decorateFunctionHelp(suggestionPanel);
}

function updateComposerState() {
  if (!sendButton || !turnInput) return;
  sendButton.textContent = turnInput.value.trim() ? "Send" : "Continue";
}

function historyOpenState() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_OPEN_STATE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveHistoryOpenState(value) {
  try {
    localStorage.setItem(HISTORY_OPEN_STATE_KEY, JSON.stringify(value));
  } catch {
    // Local storage can be unavailable in hardened browser modes.
  }
}

function historyGroups() {
  const groups = [];
  const byTurn = new Map();
  for (const entry of state?.history || []) {
    const turn = entry.turn ?? "?";
    const key = `turn:${turn}`;
    if (!byTurn.has(key)) {
      const group = { key, turn, entries: [] };
      byTurn.set(key, group);
      groups.push(group);
    }
    byTurn.get(key).entries.push(entry);
  }
  return groups;
}

function historySnippet(group) {
  const preferred = group.entries.find((entry) => entry.kind === "narration") || group.entries[0];
  const text = String(preferred?.content || "").replace(/\s+/g, " ").trim();
  return text ? `${text.slice(0, 150)}${text.length > 150 ? "..." : ""}` : "No visible text.";
}

function historyEntryHtml(entry) {
  return `
    <section class="historyEntry">
      <strong>${escapeHtml(entry.kind || "entry")}</strong>
      <p>${linkifyText(entry.content || "")}</p>
    </section>
  `;
}

function historyPagerHtml(pageCount) {
  if (pageCount <= 1) return "";
  return `
    <nav class="historyPager" aria-label="History pages">
      <button class="secondaryButton" data-history-page="prev" type="button" ${historyPage <= 0 ? "disabled" : ""}>Prev</button>
      <span>Page ${escapeHtml(historyPage + 1)} / ${escapeHtml(pageCount)}</span>
      <button class="secondaryButton" data-history-page="next" type="button" ${historyPage >= pageCount - 1 ? "disabled" : ""}>Next</button>
    </nav>
  `;
}

function renderHistory() {
  if (!historyEl) return;
  const groups = historyGroups();
  const pageCount = Math.max(1, Math.ceil(groups.length / HISTORY_PAGE_SIZE));
  historyPage = Math.min(Math.max(historyPage, 0), pageCount - 1);
  const openState = historyOpenState();
  const newestKey = groups[0]?.key;
  const pageGroups = groups.slice(historyPage * HISTORY_PAGE_SIZE, historyPage * HISTORY_PAGE_SIZE + HISTORY_PAGE_SIZE);
  historyEl.innerHTML = groups.length
    ? `
        ${historyPagerHtml(pageCount)}
        ${pageGroups
          .map((group) => {
            const selected = Object.prototype.hasOwnProperty.call(openState, group.key) ? Boolean(openState[group.key]) : group.key === newestKey;
            const entries = [...group.entries].reverse().map(historyEntryHtml).join("");
            return `
              <details class="historyItem historyTurn" data-history-key="${escapeHtml(group.key)}" ${selected ? "open" : ""}>
                <summary>
                  <strong>Turn ${escapeHtml(group.turn)}</strong>
                  <span>${escapeHtml(group.entries.length)} entries</span>
                  <p>${escapeHtml(historySnippet(group))}</p>
                </summary>
                <div class="historyEntries">${entries}</div>
              </details>
            `;
          })
          .join("")}
        ${historyPagerHtml(pageCount)}
      `
    : `<p class="empty">No history yet.</p>`;
}

function statCard(label, value) {
  return `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function profileLine(profile) {
  if (!profile || typeof profile !== "object") return "";
  return Object.entries(profile)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim())
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");
}

function npcCombatLine(npc) {
  const profile = npc?.combat_profile || {};
  const maxHealth = Number(profile.max_health ?? npc?.max_health ?? 0) || 0;
  if (!maxHealth) return "";
  const health = Number(profile.health ?? npc?.health ?? maxHealth) || 0;
  const attackMin = Number(profile.attack_min ?? npc?.attack_min ?? 0) || 0;
  const attackMax = Number(profile.attack_max ?? npc?.attack_max ?? 0) || 0;
  const defense = Number(profile.defense ?? npc?.defense ?? 0) || 0;
  const dodge = Number(profile.dodge ?? npc?.dodge ?? 0) || 0;
  return `HP ${health}/${maxHealth} · ATK ${attackMin}-${attackMax} · DEF ${defense} · Dodge ${dodge}`;
}

function abilityNameList(abilities) {
  if (!Array.isArray(abilities)) return "";
  return abilities
    .map((ability) => (typeof ability === "string" ? ability : ability?.name))
    .filter(Boolean)
    .join(", ");
}

function insertRef(type, code) {
  const token = refToken(type, code);
  const start = turnInput.selectionStart ?? turnInput.value.length;
  const end = turnInput.selectionEnd ?? turnInput.value.length;
  const before = turnInput.value.slice(0, start);
  const after = turnInput.value.slice(end);
  const leftSpace = before && !before.endsWith(" ") && !before.endsWith("\n") ? " " : "";
  const rightSpace = after && !after.startsWith(" ") && !after.startsWith("\n") ? " " : "";
  turnInput.value = `${before}${leftSpace}${token}${rightSpace}${after}`;
  const nextPos = before.length + leftSpace.length + token.length + rightSpace.length;
  turnInput.focus();
  turnInput.setSelectionRange(nextPos, nextPos);
}

function entityCard(type, entity, body, meta = "") {
  const token = refToken(type, entity.code);
  return `
    <article class="card entityCard" draggable="true" data-type="${escapeHtml(type)}" data-code="${escapeHtml(entity.code)}">
      <strong>
        <button class="code entityLink" data-code="${escapeHtml(entity.code)}" type="button">${escapeHtml(entity.code)}</button>
        ${escapeHtml(entityLabel(entity))}
      </strong>
      ${meta ? `<div class="meta">${meta}</div>` : ""}
      ${body ? `<p>${linkifyText(body)}</p>` : ""}
      <div class="miniActions">
        <button class="insertRefButton" data-type="${escapeHtml(type)}" data-code="${escapeHtml(entity.code)}" type="button">${escapeHtml(token)}</button>
      </div>
    </article>
  `;
}

function card(title, body, meta = "") {
  return `
    <article class="card">
      <strong>${title}</strong>
      ${meta ? `<div class="meta">${meta}</div>` : ""}
      ${body ? `<p>${linkifyText(body)}</p>` : ""}
    </article>
  `;
}

function renderBudgetCard() {
  const budget = state.model_budget || {};
  const logs = state.model_logs || [];
  const body =
    logs
      .slice(0, 8)
      .map((entry) => `T${entry.turn} ${entry.phase}: ~${entry.estimated_tokens} tokens`)
      .join(" | ") || "No model calls logged yet.";
  const warning = budget.warning
    ? `<p class="budgetWarning">Prompt budget warning: latest call is ~${escapeHtml(budget.latest_estimated_tokens)} / ${escapeHtml(budget.context_window)} tokens.</p>`
    : "";
  const memoryLine = `summaries ${escapeHtml(budget.turn_summaries ?? "?")} | consolidated facts ${escapeHtml(budget.consolidated_facts ?? 0)}`;
  return `
    <article class="card contextHealthCard">
      <strong>Context Health</strong>
      <div class="meta">window ${escapeHtml(budget.context_window || "?")} · warn @ ${escapeHtml(budget.warning_threshold || "?")} · latest ~${escapeHtml(budget.latest_estimated_tokens || 0)}</div>
      <p>${escapeHtml(memoryLine)}</p>
      <p>${escapeHtml(body)}</p>
      ${warning}
      <div class="contextHealthActions">
        <button id="consolidateMemoryButton" class="secondaryButton" type="button">Consolidate Memory</button>
        <button id="refreshHealthButton" class="secondaryButton" type="button">Refresh Health</button>
      </div>
      <div id="contextHealthStatus" class="meta"></div>
    </article>
  `;
}

function applyCompactMode(enabled) {
  document.body.classList.toggle("compact-mode", Boolean(enabled));
  try {
    window.localStorage.setItem(COMPACT_STORAGE_KEY, enabled ? "1" : "0");
  } catch (_) {
    /* ignore */
  }
  if (compactModeButton) {
    compactModeButton.textContent = enabled ? "Comfort" : "Compact";
  }
}

function isCompactModeEnabled() {
  try {
    return window.localStorage.getItem(COMPACT_STORAGE_KEY) === "1";
  } catch (_) {
    return false;
  }
}

let saveBrowserMode = "load"; // "load" | "save"
let saveBrowserSlots = [];
let saveBrowserSelected = "";
let saveBrowserBound = false;
let saveBrowserView = "characters"; // "characters" | "saves"
let saveBrowserCharacter = ""; // player_name key
let saveBrowserPage = 0;
const SAVE_BROWSER_PAGE_SIZE = 10;
const SAVE_UNKNOWN_CHARACTER = "Unknown hero";

function formatSaveWhen(iso) {
  if (!iso) return "Unknown time";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19).replace("T", " ");
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(iso);
  }
}

function saveSlotTime(slot) {
  const raw = slot?.saved_at || slot?.modified || "";
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

function characterKeyFromSlot(slot) {
  const name = String(slot?.player_name || "").trim();
  return name || SAVE_UNKNOWN_CHARACTER;
}

function setSaveBrowserStatus(message, kind = "") {
  const el = document.querySelector("#saveBrowserStatus");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("isError", kind === "error");
  el.classList.toggle("isOk", kind === "ok");
}

function closeSaveBrowser() {
  document.querySelector("#saveBrowserModal")?.classList.add("hidden");
  setSaveBrowserStatus("");
  saveBrowserView = "characters";
  saveBrowserCharacter = "";
  saveBrowserPage = 0;
}

async function fetchCampaignSlots() {
  const listResponse = await fetch("/api/campaign-slots", { cache: "no-store" });
  const listData = await listResponse.json().catch(() => ({}));
  if (!listResponse.ok) throw new Error(listData.detail || listData.error || `HTTP ${listResponse.status}`);
  const slots = Array.isArray(listData.slots) ? listData.slots : [];
  const autosave = listData.autosave_slot || "last";
  return { slots, autosave };
}

/** Group slots by character; each group’s saves sorted newest first. */
function groupSlotsByCharacter(slots) {
  const map = new Map();
  for (const slot of slots || []) {
    const key = characterKeyFromSlot(slot);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(slot);
  }
  const groups = [];
  for (const [name, list] of map.entries()) {
    list.sort((a, b) => saveSlotTime(b) - saveSlotTime(a));
    const latest = list[0] || {};
    groups.push({
      name,
      saves: list,
      count: list.length,
      latestAt: saveSlotTime(latest),
      latestLocation: String(latest.location || "Unknown place").trim() || "Unknown place",
      latestTurn: latest.turn,
      latestLevel: latest.player_level,
      hasAutosave: list.some((s) => Boolean(s.autosave) || s.slot === "last"),
    });
  }
  // Characters with most recent activity first
  groups.sort((a, b) => b.latestAt - a.latestAt || a.name.localeCompare(b.name));
  return groups;
}

function getSaveBrowserGroups() {
  return groupSlotsByCharacter(saveBrowserSlots);
}

function getCharacterSaves(characterName) {
  const group = getSaveBrowserGroups().find((g) => g.name === characterName);
  return group ? group.saves : [];
}

function updateSaveBrowserChrome() {
  const title = document.querySelector("#saveBrowserTitle");
  const sub = document.querySelector("#saveBrowserSubtitle");
  const back = document.querySelector("#saveBrowserBack");
  const footer = document.querySelector("#saveBrowserFooter");
  const pager = document.querySelector("#saveBrowserPager");
  const inSaves = saveBrowserView === "saves" && saveBrowserCharacter;

  if (back) back.classList.toggle("hidden", !inSaves);

  if (saveBrowserMode === "save") {
    if (title) title.textContent = inSaves ? `Save · ${saveBrowserCharacter}` : "Save game";
    if (sub) {
      sub.textContent = inSaves
        ? "Newest saves first · 10 per page. Overwrite one, or type a new slot name."
        : "Pick a character to browse their saves, or type a new slot name below.";
    }
    if (footer) footer.hidden = false;
  } else {
    if (title) title.textContent = inSaves ? saveBrowserCharacter : "Load game";
    if (sub) {
      sub.textContent = inSaves
        ? "Newest first · 10 per page. Select a save to continue."
        : "Choose a character to see their saves.";
    }
    if (footer) footer.hidden = true;
  }

  if (pager) {
    if (!inSaves) {
      pager.classList.add("hidden");
    } else {
      const total = getCharacterSaves(saveBrowserCharacter).length;
      const pageCount = Math.max(1, Math.ceil(total / SAVE_BROWSER_PAGE_SIZE));
      saveBrowserPage = Math.min(Math.max(0, saveBrowserPage), pageCount - 1);
      pager.classList.toggle("hidden", total <= SAVE_BROWSER_PAGE_SIZE);
      const label = document.querySelector("#saveBrowserPageLabel");
      const prev = document.querySelector("#saveBrowserPagePrev");
      const next = document.querySelector("#saveBrowserPageNext");
      const input = document.querySelector("#saveBrowserPageInput");
      if (label) label.textContent = `Page ${saveBrowserPage + 1} / ${pageCount}`;
      if (prev) prev.disabled = saveBrowserPage <= 0;
      if (next) next.disabled = saveBrowserPage >= pageCount - 1;
      if (input) {
        input.max = String(pageCount);
        input.value = String(saveBrowserPage + 1);
      }
    }
  }
}

function renderSaveBrowserList() {
  const listEl = document.querySelector("#saveBrowserList");
  const emptyEl = document.querySelector("#saveBrowserEmpty");
  if (!listEl || !emptyEl) return;

  updateSaveBrowserChrome();

  if (!saveBrowserSlots.length) {
    listEl.hidden = true;
    listEl.innerHTML = "";
    emptyEl.hidden = false;
    emptyEl.textContent =
      saveBrowserMode === "save"
        ? "No saves yet. Enter a slot name below and save this run."
        : "No saves found. Start a game, or use Continue if an autosave exists.";
    return;
  }

  emptyEl.hidden = true;
  listEl.hidden = false;

  if (saveBrowserView !== "saves" || !saveBrowserCharacter) {
    // Character picker
    const groups = getSaveBrowserGroups();
    listEl.innerHTML = groups
      .map((g) => {
        const when = g.latestAt ? formatSaveWhen(new Date(g.latestAt).toISOString()) : "Unknown time";
        const turn = g.latestTurn != null && g.latestTurn !== "" ? `Turn ${g.latestTurn}` : "";
        const level = g.latestLevel != null ? `Lv ${g.latestLevel}` : "";
        const bits = [turn, level, g.latestLocation].filter(Boolean).join(" · ");
        return `
          <article class="saveBrowserCard saveBrowserCharacterCard" data-character="${escapeHtml(g.name)}" tabindex="0" role="button">
            <div class="saveBrowserMeta">
              <strong>
                <span class="saveBrowserCharacterName">${escapeHtml(g.name)}</span>
                ${g.hasAutosave ? `<span class="saveBrowserBadge">Autosave</span>` : ""}
              </strong>
              <p class="saveBrowserLine">${escapeHtml(g.count)} save${g.count === 1 ? "" : "s"}</p>
              <p class="saveBrowserSub">Latest: ${escapeHtml(bits || "—")} · ${escapeHtml(when)}</p>
            </div>
            <div class="saveBrowserActions">
              <button type="button" class="chipBtn" data-open-character="${escapeHtml(g.name)}">Open</button>
            </div>
          </article>
        `;
      })
      .join("");
    return;
  }

  // Saves for one character — newest first, paginated
  const all = getCharacterSaves(saveBrowserCharacter);
  const pageCount = Math.max(1, Math.ceil(all.length / SAVE_BROWSER_PAGE_SIZE));
  saveBrowserPage = Math.min(Math.max(0, saveBrowserPage), pageCount - 1);
  const start = saveBrowserPage * SAVE_BROWSER_PAGE_SIZE;
  const pageSlots = all.slice(start, start + SAVE_BROWSER_PAGE_SIZE);

  if (!pageSlots.length) {
    listEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.textContent = `No saves for ${saveBrowserCharacter}.`;
    return;
  }

  listEl.innerHTML = pageSlots
    .map((slot) => {
      const name = String(slot.slot || "unnamed");
      const isAuto = Boolean(slot.autosave) || name === "last";
      const location = String(slot.location || "Unknown place").trim() || "Unknown place";
      const turn = slot.turn != null && slot.turn !== "" ? `Turn ${slot.turn}` : "Turn ?";
      const level = slot.player_level != null ? `Lv ${slot.player_level}` : "";
      const when = formatSaveWhen(slot.saved_at || slot.modified);
      const hist = slot.history_count != null ? `${slot.history_count} journal` : "";
      const map = slot.has_map === false ? "No map" : slot.has_map ? "Map" : "";
      const bits = [turn, level, hist, map].filter(Boolean).join(" · ");
      const selected = saveBrowserSelected === name ? "isSelected" : "";
      const autoClass = isAuto ? "isAutosave" : "";
      return `
        <article class="saveBrowserCard ${selected} ${autoClass}" data-slot="${escapeHtml(name)}" tabindex="0" role="button" aria-pressed="${saveBrowserSelected === name ? "true" : "false"}">
          <div class="saveBrowserMeta">
            <strong>
              <span class="saveBrowserSlotName">${escapeHtml(name)}</span>
              ${isAuto ? `<span class="saveBrowserBadge">Autosave</span>` : ""}
            </strong>
            <p class="saveBrowserLine">${escapeHtml(location)}</p>
            <p class="saveBrowserSub">${escapeHtml(bits || "Campaign slot")} · ${escapeHtml(when)}</p>
          </div>
          <div class="saveBrowserActions">
            ${
              saveBrowserMode === "load"
                ? `<button type="button" class="chipBtn" data-save-load="${escapeHtml(name)}">Load</button>`
                : `<button type="button" class="chipBtn" data-save-overwrite="${escapeHtml(name)}">Overwrite</button>`
            }
            <button type="button" class="chipBtn secondaryButton" data-save-delete="${escapeHtml(name)}" title="Delete this slot">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");

  updateSaveBrowserChrome();
}

function openSaveBrowserCharacter(name) {
  saveBrowserCharacter = String(name || "").trim() || SAVE_UNKNOWN_CHARACTER;
  saveBrowserView = "saves";
  saveBrowserPage = 0;
  const saves = getCharacterSaves(saveBrowserCharacter);
  if (saves[0]?.slot) saveBrowserSelected = String(saves[0].slot);
  renderSaveBrowserList();
  setSaveBrowserStatus(
    `${saves.length} save${saves.length === 1 ? "" : "s"} for ${saveBrowserCharacter} · newest first`,
    saves.length ? "ok" : "",
  );
}

function backToSaveBrowserCharacters() {
  saveBrowserView = "characters";
  saveBrowserCharacter = "";
  saveBrowserPage = 0;
  renderSaveBrowserList();
  const groups = getSaveBrowserGroups();
  setSaveBrowserStatus(
    groups.length
      ? `${groups.length} character${groups.length === 1 ? "" : "s"} · ${saveBrowserSlots.length} save${saveBrowserSlots.length === 1 ? "" : "s"}`
      : "No saves yet",
    groups.length ? "ok" : "",
  );
}

function setSaveBrowserPage(pageIndex) {
  const total = getCharacterSaves(saveBrowserCharacter).length;
  const pageCount = Math.max(1, Math.ceil(total / SAVE_BROWSER_PAGE_SIZE));
  saveBrowserPage = Math.min(Math.max(0, pageIndex), pageCount - 1);
  renderSaveBrowserList();
}

async function refreshSaveBrowser() {
  setSaveBrowserStatus("Refreshing…");
  try {
    const { slots } = await fetchCampaignSlots();
    // Always newest first globally; character grouping re-sorts per character
    saveBrowserSlots = slots.slice().sort((a, b) => saveSlotTime(b) - saveSlotTime(a));

    // If we were drilling into a character that vanished, go back up
    if (saveBrowserView === "saves" && saveBrowserCharacter) {
      const still = getCharacterSaves(saveBrowserCharacter);
      if (!still.length) {
        saveBrowserView = "characters";
        saveBrowserCharacter = "";
        saveBrowserPage = 0;
      } else if (saveBrowserSelected && !still.some((s) => s.slot === saveBrowserSelected)) {
        saveBrowserSelected = String(still[0].slot || "");
      }
    }

    renderSaveBrowserList();
    const nameInput = document.querySelector("#saveBrowserNameInput");
    if (nameInput && saveBrowserMode === "save" && !nameInput.value.trim()) {
      const defaultName =
        state?.player?.name
          ? String(state.player.name).replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 40)
          : "main";
      nameInput.value = defaultName || "main";
    }

    if (saveBrowserView === "saves" && saveBrowserCharacter) {
      const n = getCharacterSaves(saveBrowserCharacter).length;
      setSaveBrowserStatus(
        `${n} save${n === 1 ? "" : "s"} for ${saveBrowserCharacter} · newest first`,
        n ? "ok" : "",
      );
    } else {
      const groups = getSaveBrowserGroups();
      setSaveBrowserStatus(
        groups.length
          ? `${groups.length} character${groups.length === 1 ? "" : "s"} · ${saveBrowserSlots.length} total save${saveBrowserSlots.length === 1 ? "" : "s"}`
          : "No saves yet",
        groups.length ? "ok" : "",
      );
    }
  } catch (error) {
    saveBrowserSlots = [];
    renderSaveBrowserList();
    setSaveBrowserStatus(error.message || String(error), "error");
  }
}

function openSaveBrowser(mode = "load") {
  saveBrowserMode = mode === "save" ? "save" : "load";
  saveBrowserView = "characters";
  saveBrowserCharacter = "";
  saveBrowserPage = 0;
  saveBrowserSelected = "";
  const modal = document.querySelector("#saveBrowserModal");
  modal?.classList.remove("hidden");
  bindSaveBrowserOnce();
  refreshSaveBrowser();
  if (saveBrowserMode === "save") {
    document.querySelector("#saveBrowserNameInput")?.focus();
  }
}

async function loadCampaignSlotByName(slotName) {
  const trimmed = String(slotName || "").trim();
  if (!trimmed) throw new Error("Slot name is required.");
  setSaveBrowserStatus(`Loading “${trimmed}”…`);
  const response = await fetch("/api/campaign-slots/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot: trimmed }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
  const nextState =
    payload?.state && typeof payload.state === "object"
      ? payload.state
      : payload?.setup_complete != null || payload?.history
        ? payload
        : await (await fetch("/api/state")).json();
  closeSaveBrowser();
  await enterPlayFromSave(nextState, { resume: payload.resume || null });
  if (latestOutput) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = `Loaded campaign slot: ${trimmed}`;
    latestOutput.prepend(note);
  }
  const menuStatus = document.querySelector("#mainMenuStatus");
  if (menuStatus) menuStatus.textContent = `Loaded “${trimmed}”.`;
  await refreshContinueButton();
}

async function saveCampaignSlotByName(slotName) {
  const trimmed = String(slotName || "").trim();
  if (!trimmed) throw new Error("Slot name is required.");
  if (trimmed === "last") {
    if (!window.confirm("Overwrite the Continue autosave slot “last”?")) return;
  }
  setSaveBrowserStatus(`Saving “${trimmed}”…`);
  const response = await fetch("/api/campaign-slots/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot: trimmed }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  if (latestOutput) {
    latestOutput.innerHTML = paragraphs(`Saved campaign slot: ${data.slot || trimmed}`);
  }
  setSaveBrowserStatus(`Saved “${data.slot || trimmed}”.`, "ok");
  // After save, jump into that character’s list if we know the name
  const playerName = String(state?.player?.name || data.player_name || "").trim();
  await refreshSaveBrowser();
  if (playerName) {
    openSaveBrowserCharacter(playerName);
  }
  await refreshContinueButton();
}

async function deleteCampaignSlotByName(slotName) {
  const trimmed = String(slotName || "").trim();
  if (!trimmed) return;
  const label = trimmed === "last" ? "autosave “last”" : `“${trimmed}”`;
  if (!window.confirm(`Delete save ${label}? This cannot be undone.`)) return;
  setSaveBrowserStatus(`Deleting ${label}…`);
  const response = await fetch("/api/campaign-slots/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot: trimmed }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  if (saveBrowserSelected === trimmed) saveBrowserSelected = "";
  setSaveBrowserStatus(`Deleted ${label}.`, "ok");
  await refreshSaveBrowser();
  await refreshContinueButton();
}

function bindSaveBrowserOnce() {
  if (saveBrowserBound) return;
  saveBrowserBound = true;
  const modal = document.querySelector("#saveBrowserModal");
  document.querySelector("#closeSaveBrowser")?.addEventListener("click", () => closeSaveBrowser());
  document.querySelector("#saveBrowserBack")?.addEventListener("click", () => backToSaveBrowserCharacters());
  modal?.addEventListener("click", (event) => {
    if (event.target?.id === "saveBrowserModal") closeSaveBrowser();
  });
  document.querySelector("#saveBrowserConfirmSave")?.addEventListener("click", () => {
    const name = document.querySelector("#saveBrowserNameInput")?.value || saveBrowserSelected;
    saveCampaignSlotByName(name).catch((error) => setSaveBrowserStatus(error.message || String(error), "error"));
  });
  document.querySelector("#saveBrowserNameInput")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const name = event.currentTarget.value;
    if (saveBrowserMode === "save") {
      saveCampaignSlotByName(name).catch((error) => setSaveBrowserStatus(error.message || String(error), "error"));
    }
  });

  document.querySelector("#saveBrowserPagePrev")?.addEventListener("click", () => setSaveBrowserPage(saveBrowserPage - 1));
  document.querySelector("#saveBrowserPageNext")?.addEventListener("click", () => setSaveBrowserPage(saveBrowserPage + 1));
  document.querySelector("#saveBrowserPageInput")?.addEventListener("change", (event) => {
    const n = Number(event.currentTarget.value);
    if (Number.isFinite(n)) setSaveBrowserPage(n - 1);
  });

  document.querySelector("#saveBrowserList")?.addEventListener("click", (event) => {
    const openChar = event.target.closest("[data-open-character]");
    if (openChar) {
      event.preventDefault();
      openSaveBrowserCharacter(openChar.getAttribute("data-open-character"));
      return;
    }
    const charCard = event.target.closest("[data-character]");
    if (charCard && !event.target.closest("button")) {
      openSaveBrowserCharacter(charCard.getAttribute("data-character"));
      return;
    }

    const loadBtn = event.target.closest("[data-save-load]");
    if (loadBtn) {
      event.preventDefault();
      loadCampaignSlotByName(loadBtn.getAttribute("data-save-load")).catch((error) =>
        setSaveBrowserStatus(error.message || String(error), "error"),
      );
      return;
    }
    const overwriteBtn = event.target.closest("[data-save-overwrite]");
    if (overwriteBtn) {
      event.preventDefault();
      const name = overwriteBtn.getAttribute("data-save-overwrite");
      const input = document.querySelector("#saveBrowserNameInput");
      if (input) input.value = name || "";
      saveBrowserSelected = name || "";
      renderSaveBrowserList();
      if (window.confirm(`Overwrite save “${name}”?`)) {
        saveCampaignSlotByName(name).catch((error) => setSaveBrowserStatus(error.message || String(error), "error"));
      }
      return;
    }
    const delBtn = event.target.closest("[data-save-delete]");
    if (delBtn) {
      event.preventDefault();
      deleteCampaignSlotByName(delBtn.getAttribute("data-save-delete")).catch((error) =>
        setSaveBrowserStatus(error.message || String(error), "error"),
      );
      return;
    }
    const card = event.target.closest("[data-slot]");
    if (card) {
      saveBrowserSelected = card.getAttribute("data-slot") || "";
      const input = document.querySelector("#saveBrowserNameInput");
      if (input && saveBrowserMode === "save") input.value = saveBrowserSelected;
      renderSaveBrowserList();
      if (saveBrowserMode === "load" && event.detail === 2) {
        loadCampaignSlotByName(saveBrowserSelected).catch((error) =>
          setSaveBrowserStatus(error.message || String(error), "error"),
        );
      }
    }
  });
  document.querySelector("#saveBrowserList")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const charCard = event.target.closest("[data-character]");
    if (charCard) {
      event.preventDefault();
      openSaveBrowserCharacter(charCard.getAttribute("data-character"));
      return;
    }
    const card = event.target.closest("[data-slot]");
    if (!card) return;
    event.preventDefault();
    const name = card.getAttribute("data-slot");
    if (saveBrowserMode === "load") {
      loadCampaignSlotByName(name).catch((error) => setSaveBrowserStatus(error.message || String(error), "error"));
    } else {
      saveBrowserSelected = name || "";
      const input = document.querySelector("#saveBrowserNameInput");
      if (input) input.value = saveBrowserSelected;
      renderSaveBrowserList();
    }
  });
}

async function saveCampaignSlotPrompt() {
  openSaveBrowser("save");
}

async function loadCampaignSlotPrompt() {
  openSaveBrowser("load");
}

async function consolidateMemoryNow(statusEl) {
  if (statusEl) statusEl.textContent = "Consolidating...";
  const response = await fetch("/api/memory/consolidate", { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  if (statusEl) {
    statusEl.textContent = data.skipped
      ? `Skipped: ${data.reason || "not needed"} (facts ${data.facts_total ?? "?"})`
      : `Added ${data.facts_added ?? 0} facts · total ${data.facts_total ?? "?"}`;
  }
  await loadState();
}

function renderRewindCard() {
  const points = state.rewind_points || [];
  const buttons = points.length
    ? points
        .map(
          (point) =>
            `<button class="rewindPointButton" data-snapshot-id="${escapeHtml(point.id)}" type="button">Turn ${escapeHtml(point.turn)} ← Rewind</button>`,
        )
        .join("")
    : `<p class="empty">No rewind points yet.</p>`;
  return `
    <article class="card">
      <strong>Rewind</strong>
      <div class="rewindList">${buttons}</div>
    </article>
  `;
}

function renderPlayerAliases() {
  const aliases = state.player_aliases || [];
  const activeAlias = state.active_player_alias;
  const rows = aliases.length
    ? aliases
        .map((alias) => {
          const isActive = Boolean(alias.active);
          const disguised = Boolean(alias.disguised);
          return `
            <article class="playerAliasRow${isActive ? " active" : ""}">
              <div>
                <strong>${escapeHtml(alias.alias)}</strong>
                <div class="meta">Reputation ${escapeHtml(alias.reputation ?? 0)} · ${isActive ? "active" : "inactive"} · ${disguised ? "disguised" : "not disguised"}</div>
                ${alias.notes ? `<p>${linkifyText(alias.notes)}</p>` : ""}
              </div>
              <div class="miniActions">
                <button class="playerAliasActivate" data-player-alias-id="${escapeHtml(alias.id)}" type="button" ${isActive ? "disabled" : ""}>Use</button>
                ${isActive ? `<button class="playerAliasDeactivate" type="button">Stop</button>` : ""}
              </div>
              <form class="playerAliasStateForm" data-player-alias-id="${escapeHtml(alias.id)}">
                <label class="inlineCheck"><input name="disguised" type="checkbox" ${disguised ? "checked" : ""} /> Disguised</label>
                <input name="disguise_description" maxlength="300" placeholder="Worn disguise or presentation" value="${escapeHtml(alias.disguise_description || "")}" />
                <button class="secondaryButton" type="submit">Save State</button>
              </form>
            </article>
          `;
        })
        .join("")
    : `<p class="empty">No gameplay aliases yet.</p>`;
  return `
    <section class="playerAliasPanel">
      <header>
        <strong>Gameplay Aliases</strong>
        <span>${activeAlias ? `Active: ${escapeHtml(activeAlias.alias)}` : "No active alias"}</span>
      </header>
      <form id="playerAliasForm" class="playerAliasForm">
        <input name="alias" maxlength="80" placeholder="New player alias" />
        <input name="notes" maxlength="900" placeholder="Optional context" />
        <button type="submit">Create</button>
      </form>
      <div class="playerAliasList">${rows}</div>
    </section>
  `;
}

function playerPortraitSignature() {
  const player = state?.player || {};
  const inv = (state?.inventory || [])
    .map((i) => `${i.name}|${i.equipped_slot || ""}|${i.quantity || 0}`)
    .join(";");
  const cond = (state?.conditions || []).map((c) => c.name || c.summary || "").join(";");
  return `${player.name}|${player.level}|${player.title}|${inv}|${cond}`;
}

function playerFaceUrl() {
  return (
    state?.player_portrait?.data_url ||
    localStorage.getItem("morkyn-player-portrait") ||
    ""
  );
}

function playerFullbodyUrl() {
  return (
    state?.player_fullbody?.data_url ||
    localStorage.getItem("morkyn-player-fullbody") ||
    ""
  );
}

function playerPortraitHtml() {
  const face = playerFaceUrl();
  const body = playerFullbodyUrl();
  const sig = playerPortraitSignature();
  const stale = localStorage.getItem("morkyn-player-portrait-sig") && localStorage.getItem("morkyn-player-portrait-sig") !== sig;
  return `
    <section class="playerPortraitCard playerArtCard">
      <div class="playerArtPair">
        <div class="playerFaceChip artDropZone ${face ? "hasArt" : ""}" id="playerFaceFrame" data-art-slot="player-face" title="Face — drop image or generate">
          ${
            face
              ? `${artClearButtonHtml("player-face")}<img src="${face}" alt="Player face" draggable="true" />`
              : `<div class="npcPortraitPlaceholder"><span>Face</span><small>drop / gen</small></div>`
          }
        </div>
        <div class="playerFullbodyFrame artDropZone ${body || face ? "hasArt" : ""}" id="playerFullbodyFrame" data-art-slot="player-fullbody" title="Full body — drop image or generate">
          ${
            body
              ? `${artClearButtonHtml("player-fullbody")}<img src="${body}" alt="Player full body" draggable="true" />`
              : face
                ? `${artClearButtonHtml("player-fullbody")}<img src="${face}" alt="Player (face only so far)" class="playerArtFallback" draggable="true" />`
                : `<div class="npcPortraitPlaceholder"><span>Full body</span><small>drop / gen</small></div>`
          }
        </div>
      </div>
      <div class="playerPortraitMeta">
        <strong>Character art</strong>
        <p class="empty">Player only — not covered by NPC auto-gen. ${stale ? "<em>Gear/level changed — regenerate recommended.</em>" : ""}</p>
        <p class="empty" id="playerArtStatus" hidden></p>
        <div class="npcStageActions artKindActions">
          <select id="playerArtGenKind" class="artGenSelect" title="What to generate">
            <option value="both" selected>Face + body</option>
            <option value="face">Face only</option>
            <option value="fullbody">Body only</option>
          </select>
          <button type="button" class="secondaryButton compactButton" id="playerPortraitRegen" data-player-portrait-regen>Generate</button>
          <button type="button" class="secondaryButton compactButton" data-requires-forge-image data-open-image-studio data-title-online="Image Studio" title="Image Studio">Studio…</button>
          <button type="button" class="secondaryButton compactButton" data-requires-forge-image data-open-image-browser data-title-online="Image Library" title="Image Library">Library ⧉</button>
          <button type="button" class="secondaryButton compactButton" data-popout="player">Pop out ⧉</button>
        </div>
      </div>
    </section>
  `;
}

function renderPlayer() {
  const player = state.player || {};
  const skills = state.skills || [];
  const abilities = state.abilities || [];
  const aliases = state.aliases || [];
  const options = state.settings?.playthrough_options || {};
  const equipmentEffects = state.equipment_effects || {};
  const effectiveStats = profileLine(player.effective_stats || equipmentEffects.stat_modifiers);
  const equipmentAbilityNames = abilityNameList(equipmentEffects.granted_abilities);
  const formerLifeParts = [
    player.previous_life_age || options.previous_life_age ? `age ${player.previous_life_age || options.previous_life_age}` : "",
    player.previous_life_sex || options.previous_life_sex ? `sex ${player.previous_life_sex || options.previous_life_sex}` : "",
  ].filter(Boolean);
  const identityParts = [
    player.name ? `Name: ${player.name}` : "",
    player.public_name ? `Known as: ${player.public_name}` : "",
    player.title ? `Title: ${player.title}` : "",
    player.age ? `Age: ${player.age}` : "",
    player.sex ? `Sex: ${player.sex}` : "",
    formerLifeParts.length ? `Former life: ${formerLifeParts.join(", ")}` : "",
    player.backstory_mode ? `Backstory: ${player.backstory_mode}` : "",
    player.memory_policy ? `Memory: ${player.memory_policy}` : "",
    player.backstory ? `Notes: ${player.backstory}` : "",
  ].filter(Boolean);
  const conditions = (state.conditions || [])
    .map((c) => (typeof c === "string" ? c : c.name || c.summary || ""))
    .filter(Boolean)
    .join(" · ");
  return `
    ${playerPortraitHtml()}
    <div class="statGrid">
      ${statCard("Health", `${player.health ?? 0}/${player.max_health ?? 0}`)}
      ${statCard("Level", options.leveling_system === false ? "Off" : player.level ?? 1)}
      ${statCard("XP", options.leveling_system === false ? "Off" : player.xp ?? 0)}
      ${statCard("Gold", player.gold ?? 0)}
      ${statCard("Karma", player.karma ?? 0)}
    </div>
    ${card("Identity", identityParts.join(" | ") || "No identity details recorded.")}
    ${conditions ? card("Conditions", conditions) : ""}
    ${effectiveStats || equipmentAbilityNames ? card("Effective Equipment Effects", [effectiveStats ? `Stats: ${effectiveStats}` : "", equipmentAbilityNames ? `Abilities: ${equipmentAbilityNames}` : ""].filter(Boolean).join(" | "), "Active while equipped") : ""}
    ${renderPlayerAliases()}
    ${card("Entity Aliases", aliases.map((a) => `${a.alias} -> ${a.entity_code}`).join(", ") || "No entity aliases yet.")}
    ${card(
      "Karma History",
      (state.karma_history || [])
        .slice(0, 8)
        .map((entry) => `T${entry.turn}: ${entry.delta > 0 ? "+" : ""}${entry.delta} (${entry.visibility}) ${entry.reason}`)
        .join(" | ") || "No karma changes yet.",
    )}
    ${renderBudgetCard()}
    ${renderRewindCard()}
    ${skills.map((skill) => card(escapeHtml(skill.name), skill.notes || "", `Value ${escapeHtml(skill.value)}`)).join("")}
    ${abilities
      .map((ability) =>
        card(
          `${escapeHtml(ability.name)}${ability.locked ? ' <span class="warn">Locked</span>' : ""}`,
          [
            ability.base_description || ability.description,
            ability.cost ? `Cost: ${ability.cost}` : "",
            ability.prerequisites ? `Prerequisites: ${ability.prerequisites}` : "",
            ability.growth_math ? `Growth math: ${ability.growth_math}` : "",
            ability.additions ? `Added notes: ${ability.additions}` : "",
          ]
            .filter(Boolean)
            .join(" | "),
          ability.source,
        ),
      )
      .join("")}
  `;
}

function inventoryMeter(label, value, max, options = {}) {
  const numericValue = Number(value || 0);
  const numericMax = max === null || max === undefined ? null : Number(max || 0);
  const percent = numericMax ? Math.min(100, Math.max(0, (numericValue / numericMax) * 100)) : 100;
  const displayMax = numericMax === null ? "inf" : Number.isFinite(numericMax) ? numericMax : "?";
  const danger = numericMax !== null && numericValue > numericMax;
  return `
    <div class="inventoryMeter${danger ? " danger" : ""}">
      <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(numericValue)} / ${escapeHtml(displayMax)}</strong></div>
      <div class="meterTrack"><span style="width: ${percent}%"></span></div>
      ${options.note ? `<p>${escapeHtml(options.note)}</p>` : ""}
    </div>
  `;
}

function rarityClass(value) {
  return `rarity-${String(value || "common").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function itemMeta(item) {
  const enchantments = Array.isArray(item.enchantments) ? item.enchantments.filter(Boolean) : [];
  const statModifiers = profileLine(item.stat_modifiers);
  const grantedAbilities = abilityNameList(item.granted_abilities);
  return [
    item.item_type || "misc",
    item.rarity || "common",
    `qty ${item.quantity ?? 0}`,
    `wt ${item.weight ?? 0}`,
    `slots ${item.slot_size ?? 0}`,
    item.equipped_slot ? `equipped ${item.equipped_slot}` : "packed",
    enchantments.length ? `enchanted: ${enchantments.join(", ")}` : "",
    statModifiers ? `stats: ${statModifiers}` : "",
    grantedAbilities ? `abilities: ${grantedAbilities}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function renderInventory() {
  const inventory = state.inventory || [];
  const slots = state.equipment_slots || [];
  const modifiers = state.inventory_capacity_modifiers || [];
  const summary = state.inventory_summary || {};
  const options = state.settings?.playthrough_options || {};
  const slotItems = new Map();
  inventory.forEach((item) => {
    if (!item.equipped_slot) return;
    const bucket = slotItems.get(item.equipped_slot) || [];
    bucket.push(item);
    slotItems.set(item.equipped_slot, bucket);
  });
  const equippedSlots = slots
    .map((slot) => {
      const items = slotItems.get(slot.code) || [];
      const names = items.map((item) => `${item.name} x${item.quantity}`).join("\n");
      const source = slot.source_item_code ? ` · from ${escapeHtml(slot.source_item_code)}` : "";
      return `
        <article class="equipmentSlot" title="${escapeHtml(names || slot.notes || "Empty")}">
          <header>
            <strong>${escapeHtml(slot.name)}</strong>
            <span>${escapeHtml(items.length)} / ${escapeHtml(slot.capacity || 1)}</span>
          </header>
          <div class="slotSocket${items.length ? " filled" : ""}">${items.length ? items.map((item) => `<span>${escapeHtml(item.name)}</span>`).join("") : "Empty"}</div>
          <p>${escapeHtml(slot.category || "gear")}${source}</p>
        </article>
      `;
    })
    .join("");
  const itemRows = inventory.length
    ? inventory
        .map((item) => {
          const enchantments = Array.isArray(item.enchantments) ? item.enchantments.filter(Boolean) : [];
          return `
            <article class="inventoryItem ${rarityClass(item.rarity)}">
              <div>
                <strong>${escapeHtml(item.name)}</strong>
                <span>${escapeHtml(item.code || "")}</span>
              </div>
              <p>${linkifyText(item.description || "No description.")}</p>
              <div class="itemMeta">${escapeHtml(itemMeta(item))}</div>
              ${enchantments.length ? `<div class="enchantmentLine">${enchantments.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
            </article>
          `;
        })
        .join("")
    : `<p class="empty">No carried items.</p>`;
  const modifierRows = modifiers.length
    ? `<div class="capacityModifierList">${modifiers
        .map((modifier) => `<span>${escapeHtml(modifier.source)} · +${escapeHtml(modifier.weight_bonus || 0)} wt · +${escapeHtml(modifier.slot_bonus || 0)} slots${modifier.dimensional_space ? " · dimensional" : ""}</span>`)
        .join("")}</div>`
    : "";
  return `
    <section class="inventoryWindow">
      <header class="inventoryHeader">
        <div>
          <strong>Inventory</strong>
          <span>${escapeHtml(options.loot_rarity || "earned and uncommon")}</span>
        </div>
        <div class="inventorySeal">${summary.dimensional_spaces ? "Dimensional" : "Mundane"}</div>
      </header>
      <div class="inventoryMeters">
        ${inventoryMeter("Weight", summary.effective_weight ?? 0, summary.weight_capacity ?? 0, { note: summary.over_weight ? `Over by ${summary.over_weight}` : `Base ${summary.base_weight_capacity ?? 0}` })}
        ${inventoryMeter("Slots", summary.slots_used ?? 0, summary.slot_capacity_infinite ? null : summary.slot_capacity ?? 0, { note: summary.over_slots ? `Over by ${summary.over_slots}` : `${summary.equipment_slot_count ?? 0} equipment slots` })}
      </div>
      ${modifierRows}
      <div class="inventorySplit">
        <section class="equipmentGrid">
          <h3>Equipped</h3>
          <div>${equippedSlots || `<p class="empty">No equipment slots.</p>`}</div>
        </section>
        <section class="itemLedger">
          <h3>Carried</h3>
          <div>${itemRows}</div>
        </section>
      </div>
    </section>
  `;
}

function renderNpcs() {
  const npcs = (state.locations || []).flatMap((location) =>
    (location.npcs || []).map((npc) => ({ ...npc, place: `${location.code} ${location.name}` })),
  );
  return npcs.length
    ? npcs
        .map((npc) => {
          const combat = npcCombatLine(npc);
          const meta = [
            `${escapeHtml(npc.race || "human")} · ${escapeHtml(npc.role)} · rank ${escapeHtml(npc.rank || "F")} · ${escapeHtml(npc.attitude)} · trust ${escapeHtml(npc.trust ?? 0)} · ${escapeHtml(npc.place)}`,
            combat ? escapeHtml(combat) : "",
          ].filter(Boolean).join(" · ");
          return entityCard("npc", npc, npc.summary || "No notes.", meta);
        })
        .join("")
    : `<p class="empty">No NPCs indexed.</p>`;
}

function renderItems() {
  return state.inventory?.length
    ? state.inventory
        .map((item) => entityCard("item", item, item.description || "No description.", `quantity ${escapeHtml(item.quantity)}`))
        .join("")
    : `<p class="empty">No items indexed.</p>`;
}

function renderPlaces() {
  return state.locations?.length
    ? state.locations
        .map((location) =>
          entityCard(
            "location",
            location,
            location.summary || "No summary.",
            `${escapeHtml(location.visit_count)} visits · ${escapeHtml(location.npcs?.length || 0)} NPCs`,
          ),
        )
        .join("")
    : `<p class="empty">No places indexed.</p>`;
}

function renderEvents() {
  return state.events?.length
    ? state.events
        .map((event) =>
          entityCard(
            "event",
            event,
            event.summary || "No summary.",
            `${escapeHtml(event.status)} · ${escapeHtml(event.location_code || "")} ${escapeHtml(event.npc_code || "")}`,
          ),
        )
        .join("")
    : `<p class="empty">No events indexed.</p>`;
}

function renderTalk() {
  return state.conversations?.length
    ? state.conversations
        .map((talk) =>
          card(
            `${escapeHtml(talk.npc_code || "?")} ${escapeHtml(talk.npc_name || "Unknown")} · ${escapeHtml(talk.topic || "Talk")}`,
            talk.summary || "No summary.",
            `Turn ${escapeHtml(talk.turn)}`,
          ),
        )
        .join("")
    : `<p class="empty">No conversations indexed.</p>`;
}

function renderDrafts() {
  return state.response_drafts?.length
    ? state.response_drafts
        .map((draft) =>
          card(
            `${escapeHtml(draft.verdict)} · ${escapeHtml(draft.claim)}`,
            draft.notes || "No notes.",
            `${escapeHtml(draft.skill || "no skill")} DC ${escapeHtml(draft.difficulty_class)} · ${escapeHtml(draft.result)}`,
          ),
        )
        .join("")
    : `<p class="empty">No checks indexed.</p>`;
}

function renderBible() {
  const data = bible;
  if (!data) return `<p class="empty">Open this tab again to load the world bible.</p>`;
  const loc = data.active_location;
  return `
    ${loc ? entityCard("location", loc, loc.summary || "No summary.", "active location") : card("Active Location", "Unknown")}
    ${card("Player", `Health ${data.player?.health}/${data.player?.max_health}; karma ${data.player?.karma}; gold ${data.player?.gold}`)}
    ${data.important_npcs?.map((npc) => entityCard("npc", npc, npc.summary || "No notes.", `trust ${npc.trust ?? 0}`)).join("") || ""}
    ${data.active_events?.map((event) => entityCard("event", event, event.summary || "No summary.", event.status)).join("") || ""}
    ${(data.journal_highlights || []).map((entry) => card(`Turn ${escapeHtml(entry.turn)}`, entry.summary)).join("")}
  `;
}

function renderSearch() {
  const sourceHits = searchResults?.source_index?.results || [];
  return `
    <form id="searchForm" class="searchForm">
      <input id="searchInput" placeholder="Search world memory" maxlength="300" />
      <button type="submit">Search</button>
    </form>
    <div class="searchResults">
      ${
        searchResults?.results?.length
          ? searchResults.results
              .map((result) => card(`${escapeHtml(result.kind)} ${escapeHtml(result.code)} · ${escapeHtml(result.title)}`, result.text, `score ${result.score}`))
              .join("")
          : '<p class="empty">No search results yet.</p>'
      }
    </div>
    <div class="searchResults">
      ${
        sourceHits.length
          ? sourceHits
              .map((result) => card(`Source ${escapeHtml(result.source)}:${escapeHtml(result.line)} · ${escapeHtml(result.title)}`, result.text, `${escapeHtml(result.kind)} ${escapeHtml(result.code || "")} · score ${escapeHtml(result.score)}`))
              .join("")
          : ""
      }
    </div>
  `;
}

let imageConfig = null;
let imageCatalog = null;
let imageSettingsTab = "general"; // general | forge | comfyui | installs
/** Survives form re-renders so Allow search paths are not lost before Save. */
let pendingImageRoots = { forge: "", comfyui: "" };

function optionListHtml(values, selected, { allowCustom = true, emptyLabel = "(none / auto)" } = {}) {
  const list = Array.isArray(values) ? values.filter(Boolean).map(String) : [];
  const sel = String(selected || "");
  const opts = [];
  if (allowCustom) {
    opts.push(`<option value="">${escapeHtml(emptyLabel)}</option>`);
  }
  if (sel && !list.includes(sel)) {
    opts.push(`<option value="${escapeHtml(sel)}" selected>${escapeHtml(sel)} (saved)</option>`);
  }
  list.forEach((v) => {
    opts.push(`<option value="${escapeHtml(v)}" ${v === sel ? "selected" : ""}>${escapeHtml(v)}</option>`);
  });
  return opts.join("");
}

/** Collapse API titles like "foo.safetensors [abc123]" and disk "foo.safetensors". */
function normalizeCheckpointKey(name) {
  let text = String(name || "").trim().replace(/\\/g, "/");
  if (text.includes("/")) text = text.split("/").pop() || text;
  text = text.replace(/\s*\[[0-9a-fA-F]{6,64}\]\s*$/, "").trim();
  const lower = text.toLowerCase();
  for (const ext of [".safetensors", ".ckpt", ".pt", ".pth"]) {
    if (lower.endsWith(ext)) {
      text = text.slice(0, -ext.length);
      break;
    }
  }
  return text.toLowerCase().trim();
}

function dedupeCheckpointTitles(models) {
  const list = Array.isArray(models) ? models : [];
  const byKey = new Map();
  const order = [];
  for (const m of list) {
    const title = typeof m === "string" ? m : m?.title || m?.model_name || "";
    const clean = String(title || "").trim();
    if (!clean) continue;
    const key = normalizeCheckpointKey(clean) || clean.toLowerCase();
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, clean);
      order.push(key);
      continue;
    }
    // Prefer shorter clean filename over hash-suffixed API title for display
    const prevHasHash = /\[[0-9a-fA-F]{6,64}\]\s*$/.test(prev);
    const nextHasHash = /\[[0-9a-fA-F]{6,64}\]\s*$/.test(clean);
    if (prevHasHash && !nextHasHash) byKey.set(key, clean);
  }
  return order.map((k) => byKey.get(k)).filter(Boolean);
}

function forgeModelOptionsHtml(catalog, selected) {
  const models = catalog?.forge?.models || [];
  const titles = dedupeCheckpointTitles(models);
  return optionListHtml(titles, selected, { emptyLabel: "(use current Forge model)" });
}

function renderImageForm() {
  const config = imageConfig || {};
  const catalog = imageCatalog || {};
  const provider = config.provider || "off";
  const autoLaunch = config.auto_launch_if_offline === true;
  const tab = imageSettingsTab || "general";
  const forgeModels = catalog.forge?.models || [];
  const forgeSamplers = catalog.forge?.samplers || [];
  const forgeSchedulers = catalog.forge?.schedulers || [];
  const forgeVaes = catalog.forge?.vaes || [];
  const forgeUpscalers = catalog.forge?.upscalers || [];
  const comfyCkpts = dedupeCheckpointTitles(catalog.comfyui?.checkpoints || []);
  const comfySamplers = catalog.comfyui?.samplers || [];
  const comfySchedulers = catalog.comfyui?.schedulers || [];
  const comfyWorkflows =
    catalog.comfyui?.workflows || catalog.comfy_workflows_on_disk || ["txt2img_api.json"];
  const liveNote = catalog.message
    ? `<p class="empty catalogNote">${escapeHtml(catalog.message)}${catalog.ok === false ? " — start the backend and Refresh catalog." : ""}</p>`
    : `<p class="empty catalogNote">Click <strong>Refresh catalog</strong> to pull models/samplers from a running backend.</p>`;

  return `
    <form id="imageForm" class="modelForm imageForm">
      <h3 class="settingsSubhead">Images</h3>
      <p class="empty">Local Forge / ComfyUI only. Face + full-body use these settings. Default provider: <strong>off</strong>. <strong>ForgeSD is the tested path</strong>; ComfyUI is wired but not fully verified yet.</p>
      <div class="imageRepoLinks">
        <a href="https://github.com/lllyasviel/stable-diffusion-webui-forge" target="_blank" rel="noopener noreferrer">Forge GitHub</a>
        <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noopener noreferrer">ComfyUI GitHub</a>
        <a href="https://huggingface.co/InstantX/InstantID" target="_blank" rel="noopener noreferrer">InstantID (HF)</a>
        <a href="https://github.com/cubiq/ComfyUI_IPAdapter_plus" target="_blank" rel="noopener noreferrer">IPAdapter Plus</a>
      </div>
      <div class="imageSettingsTabs" role="tablist" aria-label="Image settings tabs">
        <button type="button" class="chipBtn secondaryButton imageSettingsTab ${tab === "general" ? "active" : ""}" data-image-tab="general">General</button>
        <button type="button" class="chipBtn secondaryButton imageSettingsTab ${tab === "forge" ? "active" : ""}" data-image-tab="forge">Forge / A1111</button>
        <button type="button" class="chipBtn secondaryButton imageSettingsTab ${tab === "comfyui" ? "active" : ""}" data-image-tab="comfyui">ComfyUI</button>
        <button type="button" class="chipBtn secondaryButton imageSettingsTab ${tab === "installs" ? "active" : ""}" data-image-tab="installs">Installs</button>
      </div>
      ${liveNote}

      <div class="imageTabPanel ${tab === "general" ? "open" : ""}" data-image-panel="general">
        <label>
          <span>Active provider</span>
          <select name="provider">
            <option value="off" ${provider === "off" ? "selected" : ""}>Off</option>
            <option value="demo" ${provider === "demo" ? "selected" : ""}>Demo (built-in test images)</option>
            <option value="forge" ${provider === "forge" ? "selected" : ""}>Forge / A1111</option>
            <option value="comfyui" ${provider === "comfyui" ? "selected" : ""}>ComfyUI (unverified)</option>
          </select>
        </label>
        <label class="checkboxRow">
          <input type="checkbox" name="auto_launch_if_offline" value="true" ${autoLaunch ? "checked" : ""} />
          <span>Auto-launch backend when offline (uses install root on that tab)</span>
        </label>
        <label class="checkboxRow">
          <input type="checkbox" name="auto_generate_npc_portraits" value="true" ${config.auto_generate_npc_portraits ? "checked" : ""} />
          <span>Auto-generate portraits for <strong>new NPCs</strong> in play (never the player)</span>
        </label>
        <fieldset class="faceLockSettings" style="margin:10px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px">
          <legend style="padding:0 6px;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:var(--muted)">Face lock (Face ↔ Body)</legend>
          <p class="empty" style="margin:0 0 8px">
            Keeps the same person when generating body from face (or the reverse).
            <strong>Recommended: Light</strong> — works on most PCs with Forge API.
          </p>
          <p class="empty" style="margin:0 0 10px;padding:8px 10px;border-left:3px solid color-mix(in srgb, #e0b35a 70%, var(--line));background:color-mix(in srgb, #e0b35a 12%, transparent)">
            <strong>Warning — hardware &amp; expectations:</strong>
            Face lock uses your GPU through Forge. <em>Light</em> is one extra img2img pass (more VRAM/time than a plain gen, usually fine on 6–8&nbsp;GB+).
            <em>Strong</em> tries ControlNet face models and can fail, hang, or OOM on weaker cards; InstantID over the API is unreliable on many Forge builds (Mørkyn falls back to Light).
            If gens crash, freeze, or Windows resets the driver: set mode to <strong>Light</strong> or <strong>Off</strong>, lower steps/resolution, and close other GPU apps.
          </p>
          <label>
            <span>Consistency mode</span>
            <select name="character_consistency" id="characterConsistencySelect">
              <option value="light" ${String(config.character_consistency || "light") === "light" ? "selected" : ""}>Light (recommended) — img2img face reference</option>
              <option value="auto" ${config.character_consistency === "auto" ? "selected" : ""}>Auto — Light, or Strong only if a safe ControlNet face model is registered</option>
              <option value="strong" ${config.character_consistency === "strong" ? "selected" : ""}>Strong (experimental) — ControlNet when available; falls back to Light on errors</option>
              <option value="off" ${config.character_consistency === "off" ? "selected" : ""}>Off — no face reference between images</option>
            </select>
          </label>
          <div class="modelTokenGrid" style="margin-top:8px">
            <label>
              <span>Light ref strength (denoise)</span>
              <input name="fullbody_ref_denoise" type="number" min="0.55" max="0.95" step="0.01" value="${escapeHtml(config.fullbody_ref_denoise ?? 0.88)}" title="Higher = freer full-body pose. Lower = stronger face match but may stay a bust shot." />
              <span class="empty" style="font-size:11px">Body gens place the face into a tall canvas (not stretched). Use ~0.86–0.92 if body still looks like a portrait. Lower (~0.75) = tighter face match.</span>
            </label>
            <label>
              <span>Strong lock weight</span>
              <input name="character_lock_weight" type="number" min="0.1" max="1.5" step="0.05" value="${escapeHtml(config.character_lock_weight ?? 0.65)}" title="Only used if Strong/Auto actually runs ControlNet." />
              <span class="empty" style="font-size:11px">Only applies when Strong ControlNet runs (often unused).</span>
            </label>
          </div>
          <div class="npcStageActions" style="margin-top:8px">
            <button type="button" class="secondaryButton testCharacterLock" title="Probe Forge for face-lock capability">Test face-lock</button>
          </div>
          <div data-character-lock-status class="empty" style="margin-top:6px"></div>

          <hr style="border:none;border-top:1px solid var(--line);margin:12px 0" />
          <p class="empty" style="margin:0 0 8px">
            <strong>ADetailer</strong> (optional) — after generation, detect faces and re-inpaint them for sharper detail.
            Needs the <em>adetailer</em> extension in Forge (you already have it if Test lists it).
          </p>
          <p class="empty" style="margin:0 0 10px;padding:8px 10px;border-left:3px solid color-mix(in srgb, #e0b35a 70%, var(--line));background:color-mix(in srgb, #e0b35a 12%, transparent)">
            <strong>Warning:</strong> ADetailer runs an extra detect + inpaint pass (more VRAM and time).
            On weak GPUs this can stutter, OOM, or double gen time. Start with <em>face only</em> and denoise ~0.35–0.45.
            If Forge errors on ADetailer, Mørkyn retries once without it.
          </p>
          <label class="checkboxRow">
            <input type="checkbox" name="adetailer_enable" value="true" ${config.adetailer_enable ? "checked" : ""} />
            <span>Enable ADetailer on character gens</span>
          </label>
          <label class="checkboxRow" title="ADetailer cannot take a separate ref image. When a face exists we light-lock it into the gen first, then ADetailer refines that face.">
            <input type="checkbox" name="adetailer_use_face_ref" value="true" ${config.adetailer_use_face_ref !== false ? "checked" : ""} />
            <span><strong>Use face as reference</strong> — needs an existing face image; light face lock + gentler identity-aware ADetailer</span>
          </label>
          <label class="checkboxRow">
            <input type="checkbox" name="adetailer_on_face" value="true" ${config.adetailer_on_face !== false ? "checked" : ""} />
            <span>On face / portrait</span>
          </label>
          <label class="checkboxRow">
            <input type="checkbox" name="adetailer_on_fullbody" value="true" ${config.adetailer_on_fullbody !== false ? "checked" : ""} />
            <span>On full body</span>
          </label>
          <div class="modelTokenGrid" style="margin-top:6px">
            <label>
              <span>ADetailer model</span>
              <select name="adetailer_model">
                ${["face_yolov8n.pt", "face_yolov8s.pt", "mediapipe_face_full", "mediapipe_face_short", "hand_yolov8n.pt", "person_yolov8n-seg.pt"]
                  .map((m) => {
                    const sel = String(config.adetailer_model || "face_yolov8n.pt") === m ? "selected" : "";
                    return `<option value="${escapeHtml(m)}" ${sel}>${escapeHtml(m)}</option>`;
                  })
                  .join("")}
              </select>
            </label>
            <label>
              <span>ADetailer denoise</span>
              <input name="adetailer_denoise" type="number" min="0.1" max="0.9" step="0.05" value="${escapeHtml(config.adetailer_denoise ?? 0.4)}" />
              <span class="empty" style="font-size:11px">Higher = more redraw (can drift identity). With face ref we also ease this slightly. ~0.35–0.4 is typical.</span>
            </label>
          </div>
        </fieldset>
        <label>
          <span>Default portrait style (legacy single-gen / shared identity cue)</span>
          <textarea name="portrait_style" rows="2" maxlength="800">${escapeHtml(config.portrait_style || "character portrait, face and shoulders, front view, game art")}</textarea>
        </label>
        <label>
          <span>Negative prompt (fallback if presets empty)</span>
          <textarea name="negative_prompt" rows="2" maxlength="2000">${escapeHtml(config.negative_prompt || "lowres, blurry, deformed, bad anatomy, watermark, text")}</textarea>
        </label>
        <div class="modelTokenGrid">
          <label>
            <span>Default width</span>
            <input name="default_width" type="number" min="64" max="2048" step="8" value="${escapeHtml(config.default_width ?? 512)}" />
          </label>
          <label>
            <span>Default height</span>
            <input name="default_height" type="number" min="64" max="2048" step="8" value="${escapeHtml(config.default_height ?? 512)}" />
          </label>
          <label>
            <span>Default steps</span>
            <input name="default_steps" type="number" min="1" max="150" step="1" value="${escapeHtml(config.default_steps ?? 20)}" />
          </label>
          <label>
            <span>Default CFG</span>
            <input name="default_cfg" type="number" min="1" max="30" step="0.5" value="${escapeHtml(config.default_cfg ?? 7)}" />
          </label>
          <label>
            <span>Timeout (s)</span>
            <input name="timeout_seconds" type="number" min="10" max="900" step="1" value="${escapeHtml(config.timeout_seconds ?? 180)}" />
          </label>
        </div>
        <p class="empty">Face/full-body sizes &amp; styles still live in <code>data/image_presets.json</code> (defaults: <code>config/image_presets.default.json</code>).</p>
      </div>

      <div class="imageTabPanel ${tab === "forge" ? "open" : ""}" data-image-panel="forge">
        <label>
          <span>Forge / A1111 API URL</span>
          <input name="forge_base_url" value="${escapeHtml(config.forge_base_url || "http://127.0.0.1:7860")}" maxlength="400" placeholder="http://127.0.0.1:7860" />
        </label>
        <fieldset class="iibSettings" style="margin:8px 0 12px;padding:10px 12px;border:1px solid var(--line);border-radius:8px">
          <legend style="padding:0 6px;font-size:12px;font-weight:700">Image Browser · IIB port</legend>
          <p class="empty" style="margin:0 0 8px;font-size:11px">
            Uses your installed <strong>Infinite Image Browsing</strong> extension (MIT) inside Mørkyn when Forge is up.
            Not bundled — install via <strong>Installs</strong> tab or Forge → Extensions.
            <a href="https://github.com/zanllp/sd-webui-infinite-image-browsing" target="_blank" rel="noopener noreferrer">IIB GitHub</a>
          </p>
          <label>
            <span>When IIB is available</span>
            <select name="iib_open_mode">
              <option value="embed" ${(config.iib_open_mode || "embed") === "embed" ? "selected" : ""}>Embed in Mørkyn (iframe)</option>
              <option value="tab" ${config.iib_open_mode === "tab" ? "selected" : ""}>Open in new browser tab</option>
              <option value="off" ${config.iib_open_mode === "off" ? "selected" : ""}>Off — native portraits only</option>
            </select>
          </label>
          <label>
            <span>IIB URL override <em class="muted">(optional)</em></span>
            <input name="iib_base_url" value="${escapeHtml(config.iib_base_url || "")}" maxlength="400" placeholder="Leave empty → {Forge URL}/infinite_image_browsing/" />
          </label>
          <div class="artKindActions" style="margin-top:8px">
            <button type="button" class="secondaryButton" data-open-image-browser title="Open Image Browser menu in Mørkyn">Open Image Browser</button>
            <button type="button" class="secondaryButton" data-probe-iib title="Probe IIB on disk + live API">Check IIB</button>
          </div>
          <p class="empty" id="iibProbeStatus" style="margin:6px 0 0;font-size:11px" hidden></p>
        </fieldset>
        <label>
          <span>Forge install root</span>
          <div class="pathPickerRow">
            <input name="forge_root" value="${escapeHtml(pendingImageRoots.forge || config.forge_root || "")}" maxlength="1000" placeholder="D:\\path\\to\\stable-diffusion-webui-forge" data-backend-root="forge" />
            <button class="secondaryButton browseBackendRoot" type="button" data-browse-kind="forge" title="Open a folder picker">Browse…</button>
            <button class="secondaryButton allowSearchRoot" type="button" data-search-kind="forge">Allow search</button>
          </div>
          <p class="empty">Pick your ForgeSD / webui folder with Browse, or Allow search, or paste any path. Free choice — not limited to detected installs.</p>
        </label>
        <label>
          <span>Checkpoint ${forgeModels.length ? `(${forgeModels.length} found)` : "(Refresh catalog after Save root)"}</span>
          <select name="forge_checkpoint">${forgeModelOptionsHtml(catalog, config.forge_checkpoint || "")}</select>
          <input name="forge_checkpoint_custom" value="" maxlength="400" placeholder="Or paste exact filename e.g. dreamshaperXL_lightningDPMSDE.safetensors" />
        </label>
        <p class="empty">Checkpoints are read from your Forge models folder (and live API when the backend is up). Generating uses this checkpoint via override_settings.</p>
        <label>
          <span>VAE ${forgeVaes.length ? `(${forgeVaes.length} found)` : "(Refresh catalog / set Forge root)"}</span>
          <select name="forge_vae">${optionListHtml(forgeVaes.length ? forgeVaes : ["Automatic", "None"], config.forge_vae || "", { emptyLabel: "Automatic" })}</select>
          <input name="forge_vae_custom" value="" maxlength="300" placeholder="Or paste exact VAE filename e.g. sdxl_vae.safetensors" />
        </label>
        <label>
          <span>Sampler ${forgeSamplers.length ? `(${forgeSamplers.length} found)` : "(Refresh catalog when Forge is up)"}</span>
          <select name="forge_sampler">${optionListHtml(forgeSamplers.length ? forgeSamplers : ["Euler a", "Euler", "DPM++ 2M", "DPM++ 2M SDE", "DPM++ SDE", "DDIM", "UniPC", "LCM", "Restart"], config.forge_sampler || "Euler a", { allowCustom: false })}</select>
          <input name="forge_sampler_custom" value="" maxlength="120" placeholder="Or paste exact sampler name from Forge" />
        </label>
        <label>
          <span>Scheduler ${forgeSchedulers.length ? `(${forgeSchedulers.length} found)` : ""}</span>
          <select name="forge_scheduler">${optionListHtml(forgeSchedulers.length ? forgeSchedulers : ["Automatic", "Karras", "Exponential", "SGM Uniform", "Normal", "Simple", "Beta"], config.forge_scheduler || "Automatic", { allowCustom: false })}</select>
          <input name="forge_scheduler_custom" value="" maxlength="120" placeholder="Or paste exact scheduler name" />
        </label>
        <div class="modelTokenGrid">
          <label>
            <span>CLIP skip</span>
            <input name="forge_clip_skip" type="number" min="1" max="12" step="1" value="${escapeHtml(config.forge_clip_skip ?? 1)}" />
          </label>
          <label>
            <span>Hires scale</span>
            <input name="forge_hr_scale" type="number" min="1" max="4" step="0.05" value="${escapeHtml(config.forge_hr_scale ?? 1.5)}" />
          </label>
          <label>
            <span>Denoising (hires)</span>
            <input name="forge_denoising_strength" type="number" min="0" max="1" step="0.05" value="${escapeHtml(config.forge_denoising_strength ?? 0.45)}" />
          </label>
        </div>
        <label>
          <span>Hires upscaler ${forgeUpscalers.length ? `(${forgeUpscalers.length} found)` : "(Refresh catalog / set Forge root)"}</span>
          <select name="forge_hr_upscaler">${optionListHtml(forgeUpscalers.length ? forgeUpscalers : ["Latent", "Latent (nearest-exact)", "Nearest", "ESRGAN_4x", "R-ESRGAN 4x+", "4x-UltraSharp"], config.forge_hr_upscaler || "Latent", { allowCustom: false })}</select>
          <input name="forge_hr_upscaler_custom" value="" maxlength="200" placeholder="Or paste exact upscaler name e.g. 4x-UltraSharp" />
        </label>
        <p class="empty">Samplers, VAEs, and hires upscalers come from your Forge API when online, plus models scanned under the install root. Custom paste always wins over the dropdown. Generation sends them via <code>sampler_name</code>, <code>override_settings.sd_vae</code>, and <code>hr_upscaler</code>.</p>
        <label class="checkboxRow"><input type="checkbox" name="forge_restore_faces" value="true" ${config.forge_restore_faces ? "checked" : ""} /> <span>Restore faces</span></label>
        <label class="checkboxRow"><input type="checkbox" name="forge_tiling" value="true" ${config.forge_tiling ? "checked" : ""} /> <span>Tiling</span></label>
        <label class="checkboxRow"><input type="checkbox" name="forge_enable_hr" value="true" ${config.forge_enable_hr ? "checked" : ""} /> <span>Enable hires fix</span></label>
        ${catalog.forge?.options?.sd_model_checkpoint ? `<p class="empty">Currently loaded in Forge: <code>${escapeHtml(String(catalog.forge.options.sd_model_checkpoint))}</code>${catalog.forge?.options?.sd_vae ? ` · VAE: <code>${escapeHtml(String(catalog.forge.options.sd_vae))}</code>` : ""}</p>` : ""}
      </div>

      <div class="imageTabPanel ${tab === "comfyui" ? "open" : ""}" data-image-panel="comfyui">
        <p class="empty"><strong>ComfyUI status:</strong> hooks exist (URL, root, workflow inject), but Mørkyn has <strong>not fully verified</strong> Comfy generation end-to-end yet. ForgeSD is the supported path. Once you or a contributor confirms Comfy, we’ll clear this note in the README.</p>
        <div class="imageRepoLinks">
          <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noopener noreferrer">ComfyUI GitHub</a>
        </div>
        <label>
          <span>ComfyUI API URL</span>
          <input name="comfy_base_url" value="${escapeHtml(config.comfy_base_url || "http://127.0.0.1:8188")}" maxlength="400" placeholder="http://127.0.0.1:8188" />
        </label>
        <label>
          <span>ComfyUI install root</span>
          <div class="pathPickerRow">
            <input name="comfy_root" value="${escapeHtml(pendingImageRoots.comfyui || config.comfy_root || "")}" maxlength="1000" placeholder="D:\\path\\to\\ComfyUI" data-backend-root="comfyui" />
            <button class="secondaryButton browseBackendRoot" type="button" data-browse-kind="comfyui" title="Open a folder picker">Browse…</button>
            <button class="secondaryButton allowSearchRoot" type="button" data-search-kind="comfyui">Allow search</button>
          </div>
          <p class="empty">Browse to any ComfyUI folder you own, or paste the path. Free choice.</p>
        </label>
        <label>
          <span>Checkpoint ${comfyCkpts.length ? `(${comfyCkpts.length} online)` : ""}</span>
          <select name="comfy_checkpoint">${optionListHtml(comfyCkpts, config.comfy_checkpoint || "", { emptyLabel: "(set when online / type below)" })}</select>
          <input name="comfy_checkpoint_custom" value="" maxlength="300" placeholder="Or type exact checkpoint filename" />
        </label>
        <label>
          <span>Workflow (API JSON in app/comfy_workflows/)</span>
          <select name="comfy_workflow">${optionListHtml(comfyWorkflows, config.comfy_workflow || "txt2img_api.json", { allowCustom: false, emptyLabel: "txt2img_api.json" })}</select>
        </label>
        <label>
          <span>Sampler ${comfySamplers.length ? `(${comfySamplers.length} found)` : ""}</span>
          <select name="comfy_sampler_name">${optionListHtml(comfySamplers.length ? comfySamplers : ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "ddim", "uni_pc", "lcm"], config.comfy_sampler_name || "euler", { allowCustom: false })}</select>
        </label>
        <label>
          <span>Scheduler ${comfySchedulers.length ? `(${comfySchedulers.length} found)` : ""}</span>
          <select name="comfy_scheduler">${optionListHtml(comfySchedulers.length ? comfySchedulers : ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform"], config.comfy_scheduler || "normal", { allowCustom: false })}</select>
        </label>
        <p class="empty">Workflow must be Comfy <strong>API format</strong>. Mørkyn injects prompt, size, steps, cfg, seed, checkpoint, sampler, scheduler into common nodes. Refresh catalog while Comfy is online to pull your full sampler list from <code>KSampler</code>.</p>
      </div>

      <div class="imageTabPanel ${tab === "installs" ? "open" : ""}" data-image-panel="installs">
        <p class="empty">Path-aware installs for face-lock extras. Set Forge and/or Comfy <strong>install root</strong> below (Browse any folder you want), then Save — otherwise Install stays blocked. Already present items show <strong>Installed</strong>.</p>
        <div class="imageRepoLinks">
          <a href="https://github.com/lllyasviel/stable-diffusion-webui-forge" target="_blank" rel="noopener noreferrer">Forge GitHub</a>
          <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noopener noreferrer">ComfyUI GitHub</a>
          <a href="https://huggingface.co/InstantX/InstantID" target="_blank" rel="noopener noreferrer">InstantID</a>
          <a href="https://github.com/cubiq/ComfyUI_IPAdapter_plus" target="_blank" rel="noopener noreferrer">IPAdapter Plus</a>
        </div>
        <label>
          <span>Forge install root (for InstantID / FaceID downloads)</span>
          <div class="pathPickerRow">
            <input name="forge_root" value="${escapeHtml(pendingImageRoots.forge || config.forge_root || "")}" maxlength="1000" placeholder="D:\\ForgeSD or your webui folder" data-backend-root="forge" data-installs-root="forge" />
            <button class="secondaryButton browseBackendRoot" type="button" data-browse-kind="forge">Browse…</button>
            <button class="secondaryButton allowSearchRoot" type="button" data-search-kind="forge">Allow search</button>
          </div>
        </label>
        <label>
          <span>ComfyUI install root (for custom nodes)</span>
          <div class="pathPickerRow">
            <input name="comfy_root" value="${escapeHtml(pendingImageRoots.comfyui || config.comfy_root || "")}" maxlength="1000" placeholder="D:\\path\\to\\ComfyUI" data-backend-root="comfyui" data-installs-root="comfyui" />
            <button class="secondaryButton browseBackendRoot" type="button" data-browse-kind="comfyui">Browse…</button>
            <button class="secondaryButton allowSearchRoot" type="button" data-search-kind="comfyui">Allow search</button>
          </div>
        </label>
        <p class="empty">You can point at any folder — portable packs, renamed installs, or secondary copies. Save image settings after choosing.</p>
        <div class="npcStageActions" style="margin-bottom:8px">
          <button type="button" class="secondaryButton refreshImageInstallables">Refresh install list</button>
        </div>
        <div data-image-installables class="imageInstallList">
          <p class="empty">Loading install checklist…</p>
        </div>
      </div>

      <div class="modelButtonRow">
        <button type="submit">Save image settings</button>
        <button class="secondaryButton refreshImageCatalog" type="button">Refresh catalog</button>
        <button class="secondaryButton testImageConnection" type="button">Test connection</button>
        <button class="secondaryButton checkImageReadiness" type="button">Check readiness</button>
        <button class="secondaryButton launchImageBackend" type="button">Launch backend</button>
      </div>
    </form>
    <div class="modelStatus" data-image-status></div>
    <p class="empty">Docs: <code>docs/ConnectImages.md</code>. Presets file: <code>data/image_presets.json</code>.</p>
  `;
}

function renderImageInstallablesHtml(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    return `<p class="empty">No installables returned.</p>`;
  }
  const forgeOk = data?.forge?.valid;
  const comfyOk = data?.comfyui?.valid;
  const roots = `<p class="empty">Forge root: ${
    forgeOk ? `<code>${escapeHtml(data.forge.root || "")}</code> · ready` : "<em>not set / invalid</em>"
  } · Comfy root: ${
    comfyOk ? `<code>${escapeHtml(data.comfyui.root || "")}</code> · ready` : "<em>not set / invalid</em>"
  }</p>`;
  const rows = items
    .map((item) => {
      const status = item.installed
        ? `<span class="imageInstallStatus ok">Installed</span>`
        : item.can_install
          ? `<span class="imageInstallStatus">Missing</span>`
          : `<span class="imageInstallStatus">Blocked</span>`;
      const action = item.installed
        ? ""
        : item.can_install
          ? `<button type="button" class="secondaryButton chipBtn installImageComponent" data-install-id="${escapeHtml(item.id)}">Install</button>`
          : `<button type="button" class="secondaryButton chipBtn" disabled title="${escapeHtml(item.blocked_reason || "Set install root first")}">Install</button>`;
      const links = (item.links || [])
        .map(
          (l) =>
            `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.label || l.url)}</a>`,
        )
        .join("");
      const cls = item.installed ? "installed" : item.can_install ? "" : "blocked";
      return `
        <div class="imageInstallRow ${cls}" data-install-row="${escapeHtml(item.id)}">
          <div class="imageInstallMeta">
            <strong>${escapeHtml(item.title || item.id)} <em class="muted">· ${escapeHtml(item.backend || "")}</em></strong>
            <p>${escapeHtml(item.description || "")}</p>
            ${item.detail ? `<p class="muted">${escapeHtml(String(item.detail).slice(0, 180))}</p>` : ""}
            ${links ? `<div class="installLinks">${links}</div>` : ""}
          </div>
          <div class="imageInstallActions">
            ${status}
            ${action}
          </div>
        </div>`;
    })
    .join("");
  return `${roots}${data?.note ? `<p class="empty">${escapeHtml(data.note)}</p>` : ""}<div class="imageInstallList">${rows}</div>`;
}

async function refreshImageInstallablesPanel(host) {
  const el =
    host?.querySelector?.("[data-image-installables]") ||
    document.querySelector("[data-image-installables]");
  if (!el) return null;
  el.innerHTML = `<p class="empty">Checking install roots…</p>`;
  try {
    const res = await fetch("/api/image-installables", { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || "Could not load installables");
    el.innerHTML = renderImageInstallablesHtml(data);
    return data;
  } catch (error) {
    el.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    return null;
  }
}

function themeAdapterHintList(config) {
  const known = Array.isArray(config?.theme_adapter_hints) && config.theme_adapter_hints.length
    ? config.theme_adapter_hints
    : ["isekai_rpg", "system_rpg", "grimdark", "default"];
  const map = config?.theme_adapter_map && typeof config.theme_adapter_map === "object"
    ? config.theme_adapter_map
    : {};
  const extra = Object.keys(map).filter((k) => k && !known.includes(k));
  return [...known, ...extra];
}

function currentSessionThemeModel() {
  const live =
    state?.settings?.playthrough_options?.session_theme?.theme_model ??
    state?.playthrough_options?.session_theme?.theme_model;
  if (live != null && String(live).trim()) return String(live).trim();
  if (lastSessionTheme && typeof lastSessionTheme === "object" && lastSessionTheme.theme_model) {
    return String(lastSessionTheme.theme_model).trim();
  }
  return "";
}

function currentSessionAdapterHint() {
  const live =
    state?.settings?.playthrough_options?.session_theme?.adapter_hint ??
    lastSessionTheme?.adapter_hint;
  return String(live || "").trim();
}

function mappedModelForCurrentAdapter(config) {
  const hint = currentSessionAdapterHint() || "default";
  const map = config?.theme_adapter_map && typeof config.theme_adapter_map === "object" ? config.theme_adapter_map : {};
  return String(map[hint] || map.default || "").trim();
}

function renderThemeAdapterMapFields(config) {
  const map = config?.theme_adapter_map && typeof config.theme_adapter_map === "object"
    ? config.theme_adapter_map
    : {};
  const hints = themeAdapterHintList(config);
  const rows = hints
    .map((hint) => {
      const val = map[hint] != null ? String(map[hint]) : "";
      return `
      <label>
        <span>${escapeHtml(hint)}</span>
        <input name="theme_map_${escapeHtml(hint)}" value="${escapeHtml(val)}" maxlength="200"
          placeholder="(blank = main model)" data-theme-adapter-hint="${escapeHtml(hint)}" />
      </label>`;
    })
    .join("");
  const sessionModel = currentSessionThemeModel();
  const mapped = mappedModelForCurrentAdapter(config);
  const hint = currentSessionAdapterHint();
  const sessionHint = hint
    ? `Current adapter_hint: <code>${escapeHtml(hint)}</code>${mapped ? ` · map suggests <code>${escapeHtml(mapped)}</code>` : ""}`
    : "No session theme yet — Randomize an idea or Start a run first.";
  return `
    <details class="themeAdapterMap" open>
      <summary>Theme adapter models (optional)</summary>
      <p class="empty">When a playthrough has <code>session_theme.adapter_hint</code>, turns can use a different Ollama/API model (or GGUF path for llama.cpp). Leave blank to keep the main model.</p>
      ${rows}
      <label class="sessionThemeModelField">
        <span>This session theme model</span>
        <input name="session_theme_model" value="${escapeHtml(sessionModel)}" maxlength="200"
          placeholder="${escapeHtml(mapped || "(blank = use map / main model)")}"
          data-session-theme-model="1" />
      </label>
      <p class="empty">${sessionHint} Per-session model <strong>wins</strong> over the map above. Saved with Model settings (setup) or applied live mid-run.</p>
    </details>`;
}

function renderModelForm() {
  const config = modelConfig || {};
  const provider = config.provider || "llama_cpp";
  const preset = config.api_preset || "xai";
  const keyHint = config.api_key_set
    ? `Key set${config.api_key_hint ? ` (${escapeHtml(config.api_key_hint)})` : ""} — leave blank to keep`
    : "Paste key or set XAI_API_KEY / OPENAI_API_KEY / AI_RPG_API_KEY";
  return `
    <form id="modelForm" class="modelForm">
      <label>
        <span>Provider</span>
        <select name="provider">
          <option value="llama_cpp" ${provider === "llama_cpp" ? "selected" : ""}>llama.cpp / GGUF (local)</option>
          <option value="ollama" ${provider === "ollama" ? "selected" : ""}>Ollama (local)</option>
          <option value="openai" ${provider === "openai" ? "selected" : ""}>Cloud / agent API (OpenAI-compatible)</option>
        </select>
      </label>
      <label>
        <span>API preset (cloud)</span>
        <select name="api_preset">
          <option value="xai" ${preset === "xai" ? "selected" : ""}>xAI / Grok</option>
          <option value="openai" ${preset === "openai" ? "selected" : ""}>OpenAI</option>
          <option value="custom" ${preset === "custom" ? "selected" : ""}>Custom OpenAI-compatible</option>
        </select>
      </label>
      <label>
        <span>API base URL</span>
        <input name="api_base_url" value="${escapeHtml(config.api_base_url || "https://api.x.ai/v1")}" maxlength="400" placeholder="https://api.x.ai/v1" />
      </label>
      <label>
        <span>API model</span>
        <input name="api_model" value="${escapeHtml(config.api_model || "grok-4.5")}" maxlength="200" placeholder="grok-4.5" />
      </label>
      <label>
        <span>API key</span>
        <input name="api_key" type="password" value="" maxlength="500" autocomplete="off" placeholder="${escapeHtml(keyHint)}" />
      </label>
      <label>
        <span>Model Path (GGUF)</span>
        <div class="pathPickerRow">
          <input name="gguf_model_path" value="${escapeHtml(config.gguf_model_path || DEFAULT_GGUF_MODEL)}" maxlength="1000" placeholder="D:\\path\\to\\model.gguf" />
          <button class="secondaryButton selectModelFile" type="button">Select File</button>
        </div>
      </label>
      <label>
        <span>llama.cpp Server URL</span>
        <input name="llama_cpp_base_url" value="${escapeHtml(config.llama_cpp_base_url || "http://localhost:8080")}" maxlength="300" />
      </label>
      <label>
        <span>Ollama URL</span>
        <input name="ollama_base_url" value="${escapeHtml(config.ollama_base_url || "http://localhost:11434")}" maxlength="300" />
      </label>
      <label>
        <span>Ollama Model</span>
        <input name="ollama_model" value="${escapeHtml(config.ollama_model || "llama3.1")}" maxlength="200" />
      </label>
      <div class="modelTokenGrid">
        <label>
          <span>Soft Token Target</span>
          <input name="response_token_cap" type="number" min="64" max="100000" step="1" value="${escapeHtml(config.response_token_cap ?? 1500)}" />
        </label>
        <label>
          <span>Hard Token Cap</span>
          <input name="response_token_hard_cap" type="number" min="64" max="100000" step="1" value="${escapeHtml(config.response_token_hard_cap ?? 2000)}" />
        </label>
      </div>
      ${renderThemeAdapterMapFields(config)}
      <div class="modelButtonRow">
        <button type="submit">Save Model</button>
        <button class="secondaryButton testModelConnection" type="button">Test Connection</button>
      </div>
    </form>
    <div class="modelStatus" data-model-status></div>
    <p class="empty">Local: llama.cpp / Ollama. Cloud or agents: pick OpenAI-compatible (xAI Grok default). External agents can POST to <code>/api/agent/turn</code>.</p>
    <hr class="settingsDivider" />
    ${renderImageForm()}
  `;
}

function renderModel() {
  return renderModelForm();
}

const TAB_RENDERERS = () => ({
  player: renderPlayer,
  inventory: renderInventory,
  bible: renderBible,
  search: renderSearch,
  model: renderModel,
  npcs: renderNpcs,
  items: renderItems,
  places: renderPlaces,
  events: renderEvents,
  talk: renderTalk,
  drafts: renderDrafts,
});

const TAB_LABELS = {
  player: "Player",
  inventory: "Inventory",
  bible: "Bible",
  search: "Search",
  model: "Model",
  npcs: "NPCs",
  items: "Items",
  places: "Places",
  events: "Events",
  talk: "Talk",
  drafts: "Checks",
  imageStudio: "Image Studio",
  art: "Image Studio",
  imageBrowser: "Image Browser",
  iib: "Image Browser",
};

const poppedOutTabs = new Set();
const popoutWindows = {};
const floatPanels = {};
/** Stacking order for in-page float windows (above play panels, ordered among themselves). */
let floatZ = 50;

function raiseFloatPanel(panel) {
  if (!panel) return;
  floatZ += 1;
  panel.style.zIndex = String(floatZ);
  panel.style.setProperty("--float-z", String(floatZ));
  Object.values(floatPanels).forEach((other) => {
    if (other && other !== panel) other.classList.remove("isFront");
  });
  panel.classList.add("isFront");
}

/** Prefer the viewport-fixed global host so floats work on New Game setup and play. */
function getFloatLayer() {
  return (
    document.querySelector("#globalFloatLayer") ||
    document.querySelector("#floatLayer") ||
    null
  );
}

const PLAY_LAYOUT_KEY = "morkyn-play-layout-v3";
const FLOAT_LAYOUT_KEY = "morkyn-float-windows-v1";
const PLAY_PANEL_IDS = ["chat", "map", "present", "tabs", "history"];
const DEFAULT_PANEL_WIDTHS = {
  chat: 28,
  map: 34,
  present: 12,
  tabs: 14,
  history: 12,
};

// Module state for play-panel layout + float windows (must exist before bind/boot).
let playLayout = loadPlayLayoutState();
let playLayoutBound = false;
let floatWindowState = loadFloatWindowState();

/** @returns {{ custom: boolean, rows: Array<{ height: number, panels: Array<{ id: string, width: number }> }> }} */
function makeSingleRowLayout(widthsById = DEFAULT_PANEL_WIDTHS, custom = false) {
  const panels = PLAY_PANEL_IDS.map((id) => ({
    id,
    width: Number(widthsById[id]) || DEFAULT_PANEL_WIDTHS[id] || 12,
  }));
  const norm = normalizeLayoutWeights(
    panels.map((p) => p.width),
    panels.length,
    8,
  );
  panels.forEach((p, i) => {
    p.width = norm[i];
  });
  return {
    custom: Boolean(custom),
    rows: [{ height: 100, panels }],
  };
}

function cloneDefaultPlayLayout() {
  return makeSingleRowLayout(DEFAULT_PANEL_WIDTHS, false);
}

function sceneFocusWidthMap() {
  return { chat: 38, map: 20, present: 14, tabs: 16, history: 12 };
}

function mapPrimaryWidthMap() {
  return { ...DEFAULT_PANEL_WIDTHS };
}

function loadPlayLayoutState() {
  try {
    let raw = JSON.parse(localStorage.getItem(PLAY_LAYOUT_KEY) || "null");
    if (!raw || typeof raw !== "object") {
      // Migrate v2 flat order+widths, then v1
      const v2 = JSON.parse(localStorage.getItem("morkyn-play-layout-v2") || "null");
      if (v2 && typeof v2 === "object") raw = migrateFlatPlayLayout(v2);
      else {
        const v1 = JSON.parse(localStorage.getItem("morkyn-play-layout-v1") || "null");
        if (v1 && typeof v1 === "object") raw = migrateFlatPlayLayout(migrateLegacyRailLayout(v1));
      }
    }
    if (!raw || typeof raw !== "object") return cloneDefaultPlayLayout();
    return normalizePlayLayout(raw);
  } catch {
    return cloneDefaultPlayLayout();
  }
}

function migrateLegacyRailLayout(legacy) {
  const order = Array.isArray(legacy.order) ? [...legacy.order] : ["chat", "map", "rail"];
  const expanded = order.flatMap((id) => (id === "rail" ? ["present", "tabs", "history"] : [id]));
  const widths = Array.isArray(legacy.widths) ? [...legacy.widths] : [34, 42, 24];
  if (widths.length === 3 && expanded.length === 5) {
    const railW = widths[2] || 24;
    widths.splice(2, 1, railW * 0.35, railW * 0.4, railW * 0.25);
  }
  return { custom: Boolean(legacy.custom), order: expanded, widths };
}

function migrateFlatPlayLayout(flat) {
  let order = Array.isArray(flat.order) ? flat.order.map(String) : [...PLAY_PANEL_IDS];
  if (order.includes("rail")) {
    order = order.flatMap((id) => (id === "rail" ? ["present", "tabs", "history"] : [id]));
  }
  order = order.filter((id) => PLAY_PANEL_IDS.includes(id));
  PLAY_PANEL_IDS.forEach((id) => {
    if (!order.includes(id)) order.push(id);
  });
  const widths = normalizeLayoutWeights(
    Array.isArray(flat.widths) ? flat.widths.map(Number) : order.map((id) => DEFAULT_PANEL_WIDTHS[id]),
    order.length,
    8,
  );
  return {
    custom: Boolean(flat.custom),
    rows: [
      {
        height: 100,
        panels: order.map((id, i) => ({ id, width: widths[i] })),
      },
    ],
  };
}

function normalizePlayLayout(raw) {
  // Already rows-based
  if (Array.isArray(raw.rows) && raw.rows.length) {
    const seen = new Set();
    const rows = [];
    for (const row of raw.rows) {
      const panels = [];
      for (const p of row.panels || []) {
        // Column stack cell
        if (Array.isArray(p?.stack) && p.stack.length) {
          const stack = [];
          for (const leaf of p.stack) {
            const id = String(leaf?.id || leaf || "");
            if (!PLAY_PANEL_IDS.includes(id) || seen.has(id)) continue;
            seen.add(id);
            stack.push({ id, height: Number(leaf.height) || 50 });
          }
          if (!stack.length) continue;
          if (stack.length === 1) {
            panels.push({ id: stack[0].id, width: Number(p.width) || DEFAULT_PANEL_WIDTHS[stack[0].id] || 12 });
          } else {
            const hNorm = normalizeLayoutWeights(
              stack.map((s) => s.height),
              stack.length,
              16,
            );
            stack.forEach((s, i) => {
              s.height = hNorm[i];
            });
            panels.push({
              width: Number(p.width) || 20,
              stack,
            });
          }
          continue;
        }
        const id = String(p?.id || p);
        if (!PLAY_PANEL_IDS.includes(id) || seen.has(id)) continue;
        seen.add(id);
        panels.push({ id, width: Number(p.width) || DEFAULT_PANEL_WIDTHS[id] || 12 });
      }
      if (!panels.length) continue;
      const norm = normalizeLayoutWeights(
        panels.map((p) => p.width),
        panels.length,
        8,
      );
      panels.forEach((p, i) => {
        p.width = norm[i];
      });
      rows.push({ height: Math.max(8, Number(row.height) || 100 / raw.rows.length), panels });
    }
    PLAY_PANEL_IDS.forEach((id) => {
      if (seen.has(id)) return;
      // Append missing panels to last row
      if (!rows.length) rows.push({ height: 100, panels: [] });
      rows[rows.length - 1].panels.push({ id, width: DEFAULT_PANEL_WIDTHS[id] || 12 });
      seen.add(id);
    });
    // Renormalize each row + row heights
    rows.forEach((row) => {
      const norm = normalizeLayoutWeights(
        row.panels.map((p) => p.width),
        row.panels.length,
        8,
      );
      row.panels.forEach((p, i) => {
        p.width = norm[i];
      });
      row.panels.forEach((p) => {
        if (Array.isArray(p.stack) && p.stack.length > 1) {
          const hNorm = normalizeLayoutWeights(
            p.stack.map((s) => s.height || 50),
            p.stack.length,
            16,
          );
          p.stack.forEach((s, i) => {
            s.height = hNorm[i];
          });
        }
      });
    });
    const heights = normalizeLayoutWeights(
      rows.map((r) => r.height),
      rows.length,
      12,
    );
    rows.forEach((r, i) => {
      r.height = heights[i];
    });
    return { custom: Boolean(raw.custom), rows };
  }
  // Flat fallback
  return normalizePlayLayout(migrateFlatPlayLayout(raw));
}

function loadFloatWindowState() {
  try {
    const raw = JSON.parse(localStorage.getItem(FLOAT_LAYOUT_KEY) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch {
    return {};
  }
}

function saveFloatWindowState() {
  try {
    localStorage.setItem(FLOAT_LAYOUT_KEY, JSON.stringify(floatWindowState));
  } catch {
    /* ignore */
  }
}

function normalizeLayoutWeights(values, count, minEach = 10) {
  const list = Array.from({ length: count }, (_, i) => {
    const n = Number(values[i]);
    return Number.isFinite(n) && n > 0 ? n : 100 / count;
  });
  const floor = Math.max(4, minEach);
  for (let i = 0; i < list.length; i += 1) list[i] = Math.max(floor, list[i]);
  const sum = list.reduce((a, b) => a + b, 0) || 1;
  return list.map((v) => Math.round((v / sum) * 1000) / 10);
}

function savePlayLayoutState() {
  try {
    localStorage.setItem(PLAY_LAYOUT_KEY, JSON.stringify(playLayout));
  } catch {
    /* ignore quota */
  }
}

function hasCustomPlayLayout() {
  return Boolean(playLayout?.custom);
}

function panelEl(id) {
  return document.querySelector(`[data-play-panel="${id}"]`);
}

function activeLayoutRows() {
  if (playLayout.custom && Array.isArray(playLayout.rows) && playLayout.rows.length) {
    return playLayout.rows;
  }
  // Auto mode proportions (not sticky)
  const map =
    gameView?.classList.contains("sceneFocus") || gameView?.classList.contains("isGenerating")
      ? sceneFocusWidthMap()
      : mapPrimaryWidthMap();
  return makeSingleRowLayout(map, false).rows;
}

/**
 * Layout cell = either a single panel `{ id, width }` or a column stack
 * `{ width, stack: [{ id, height }, ...] }` so "map above narrator" only stacks
 * inside that column — not a full-width row over every panel.
 */
function findPanelLocation(id, rows = playLayout.rows) {
  for (let r = 0; r < (rows || []).length; r += 1) {
    const panels = rows[r].panels || [];
    for (let c = 0; c < panels.length; c += 1) {
      const cell = panels[c];
      if (cell?.id === id) return { row: r, col: c, stackIndex: null };
      if (Array.isArray(cell?.stack)) {
        const si = cell.stack.findIndex((s) => s && s.id === id);
        if (si >= 0) return { row: r, col: c, stackIndex: si };
      }
    }
  }
  return null;
}

/** Pull a leaf panel entry out of rows; may collapse empty stacks/rows. */
function extractPanelFromRows(rows, fromLoc) {
  if (!fromLoc) return null;
  const cell = rows[fromLoc.row]?.panels?.[fromLoc.col];
  if (!cell) return null;
  if (fromLoc.stackIndex == null) {
    // Whole cell is a single panel, or we're moving the entire stack as one unit
    if (cell.id) {
      const [moved] = rows[fromLoc.row].panels.splice(fromLoc.col, 1);
      return moved ? { id: moved.id, width: moved.width || 12 } : null;
    }
    return null;
  }
  // Extract one leaf from a stack
  if (!Array.isArray(cell.stack) || !cell.stack[fromLoc.stackIndex]) return null;
  const [leaf] = cell.stack.splice(fromLoc.stackIndex, 1);
  if (!leaf) return null;
  if (cell.stack.length === 1) {
    // Flatten back to a plain panel
    const only = cell.stack[0];
    rows[fromLoc.row].panels[fromLoc.col] = { id: only.id, width: cell.width || 12 };
  } else if (cell.stack.length === 0) {
    rows[fromLoc.row].panels.splice(fromLoc.col, 1);
  } else {
    const heights = normalizeLayoutWeights(
      cell.stack.map((s) => s.height || 50),
      cell.stack.length,
      16,
    );
    cell.stack.forEach((s, i) => {
      s.height = heights[i];
    });
  }
  return { id: leaf.id, width: cell.width || 12 };
}

function rebuildPlayGridDom(rows) {
  const grid = document.querySelector("#playGrid");
  if (!grid) return;
  // Detach panels, drop old chrome
  const panels = {};
  PLAY_PANEL_IDS.forEach((id) => {
    const el = panelEl(id);
    if (el) {
      panels[id] = el;
      el.remove();
    }
  });
  grid.innerHTML = "";
  grid.classList.add("playGridFlex");

  const heights = normalizeLayoutWeights(
    rows.map((r) => r.height || 100 / rows.length),
    rows.length,
    12,
  );

  rows.forEach((row, rowIndex) => {
    const rowEl = document.createElement("div");
    rowEl.className = "playRow";
    rowEl.dataset.rowIndex = String(rowIndex);
    rowEl.style.flex = `${heights[rowIndex]} 1 0`;

    const widths = normalizeLayoutWeights(
      row.panels.map((p) => p.width),
      row.panels.length,
      8,
    );
    row.panels.forEach((p, colIndex) => {
      const widthFlex = `${widths[colIndex]} 1 0`;
      if (Array.isArray(p.stack) && p.stack.length > 1) {
        // Column-local vertical stack (e.g. map only above chat, not full grid width)
        const stackEl = document.createElement("div");
        stackEl.className = "playStack";
        stackEl.dataset.rowIndex = String(rowIndex);
        stackEl.dataset.colIndex = String(colIndex);
        stackEl.style.flex = widthFlex;
        const stackHeights = normalizeLayoutWeights(
          p.stack.map((s) => s.height || 50),
          p.stack.length,
          16,
        );
        p.stack.forEach((leaf, leafIndex) => {
          const panel = panels[leaf.id];
          if (!panel) return;
          panel.style.flex = `${stackHeights[leafIndex]} 1 0`;
          panel.dataset.rowIndex = String(rowIndex);
          panel.dataset.colIndex = String(colIndex);
          panel.dataset.stackIndex = String(leafIndex);
          stackEl.appendChild(panel);
          if (leafIndex < p.stack.length - 1) {
            const split = document.createElement("div");
            split.className = "playSplitter playSplitterStack";
            split.dataset.rowIndex = String(rowIndex);
            split.dataset.colIndex = String(colIndex);
            split.dataset.stackSplitIndex = String(leafIndex);
            split.setAttribute("role", "separator");
            split.setAttribute("aria-orientation", "horizontal");
            split.setAttribute("aria-label", "Resize stacked panels");
            split.tabIndex = 0;
            stackEl.appendChild(split);
          }
        });
        rowEl.appendChild(stackEl);
      } else {
        const id = p.id || (Array.isArray(p.stack) && p.stack[0]?.id);
        const panel = id ? panels[id] : null;
        if (!panel) return;
        panel.style.flex = widthFlex;
        panel.dataset.rowIndex = String(rowIndex);
        panel.dataset.colIndex = String(colIndex);
        delete panel.dataset.stackIndex;
        rowEl.appendChild(panel);
      }
      if (colIndex < row.panels.length - 1) {
        const split = document.createElement("div");
        split.className = "playSplitter playSplitterCol";
        split.dataset.rowIndex = String(rowIndex);
        split.dataset.splitIndex = String(colIndex);
        split.setAttribute("role", "separator");
        split.setAttribute("aria-orientation", "vertical");
        split.setAttribute("aria-label", "Resize columns");
        split.tabIndex = 0;
        rowEl.appendChild(split);
      }
    });
    grid.appendChild(rowEl);

    if (rowIndex < rows.length - 1) {
      const split = document.createElement("div");
      split.className = "playSplitter playSplitterRow";
      split.dataset.rowSplitIndex = String(rowIndex);
      split.setAttribute("role", "separator");
      split.setAttribute("aria-orientation", "horizontal");
      split.setAttribute("aria-label", "Resize rows");
      split.tabIndex = 0;
      grid.appendChild(split);
    }
  });
}

function applyPlayLayout(options = {}) {
  const grid = document.querySelector("#playGrid");
  if (!grid || !gameView) return;
  const rebuild = options.rebuild !== false;

  playLayout = normalizePlayLayout(playLayout);

  if (!playLayout.custom) {
    gameView.classList.remove("customLayout");
    // Still use flex row structure so stacking works after first vertical drop
    const rows = activeLayoutRows();
    if (rebuild) rebuildPlayGridDom(rows);
    updatePlayLayoutChrome();
    return;
  }

  gameView.classList.add("customLayout");
  if (rebuild) rebuildPlayGridDom(playLayout.rows);
  else {
    // Live resize: update flex factors only
    const rows = playLayout.rows;
    const heights = normalizeLayoutWeights(
      rows.map((r) => r.height),
      rows.length,
      12,
    );
    grid.querySelectorAll(".playRow").forEach((rowEl, rowIndex) => {
      if (!rows[rowIndex]) return;
      rowEl.style.flex = `${heights[rowIndex]} 1 0`;
      const widths = normalizeLayoutWeights(
        rows[rowIndex].panels.map((p) => p.width),
        rows[rowIndex].panels.length,
        8,
      );
      // Direct children: panels or .playStack columns (not nested panels)
      let colIndex = 0;
      [...rowEl.children].forEach((child) => {
        if (child.classList?.contains("playSplitter")) return;
        if (widths[colIndex] == null) return;
        child.style.flex = `${widths[colIndex]} 1 0`;
        const cell = rows[rowIndex].panels[colIndex];
        if (child.classList?.contains("playStack") && Array.isArray(cell?.stack)) {
          const sh = normalizeLayoutWeights(
            cell.stack.map((s) => s.height || 50),
            cell.stack.length,
            16,
          );
          child.querySelectorAll(":scope > [data-play-panel]").forEach((panel, si) => {
            if (sh[si] != null) panel.style.flex = `${sh[si]} 1 0`;
          });
        }
        colIndex += 1;
      });
    });
  }
  updatePlayLayoutChrome();
}

function updatePlayLayoutChrome() {
  const hint = document.querySelector("#playLayoutHint");
  const idle = document.querySelector("#chatIdleHint");
  const resetBtn = document.querySelector("#resetPlayLayoutBtn");
  const multiRow = (playLayout.rows || []).length > 1;
  const hintText = document.querySelector("#playLayoutHintText");
  if (hint) {
    hint.classList.toggle("hidden", !playLayout.custom);
    if (hintText && playLayout.custom) {
      hintText.textContent =
        "Custom layout — drop ⋮⋮ on top/bottom of a panel to stack in that column only (e.g. map above narrator). Left/right = side-by-side. Drag edges to resize.";
    }
  }
  if (resetBtn) {
    resetBtn.textContent = playLayout.custom ? "Layout●" : "Layout";
    resetBtn.title = playLayout.custom
      ? "Custom layout active — click to reset auto layout"
      : "Drag panel headers: drop on top/bottom to stack, left/right to place beside. Drag edges to resize.";
  }
  if (idle && playLayout.custom && !gameView?.classList.contains("isGenerating")) {
    idle.textContent = multiRow ? "Custom stacked layout" : "Custom layout (auto focus off)";
  }
}

function markCustomPlayLayout() {
  playLayout.custom = true;
  playLayout = normalizePlayLayout(playLayout);
  savePlayLayoutState();
  applyPlayLayout();
}

function resetPlayLayout() {
  playLayout = cloneDefaultPlayLayout();
  savePlayLayoutState();
  applyPlayLayout();
  setSceneFocus(false, { scroll: false, force: true });
}

/** Drop edge relative to a panel: top | bottom | left | right */
function panelDropEdge(panel, clientX, clientY) {
  const r = panel.getBoundingClientRect();
  if (!r.width || !r.height) return "right";
  const x = (clientX - r.left) / r.width;
  const y = (clientY - r.top) / r.height;
  const v = Math.min(y, 1 - y);
  const h = Math.min(x, 1 - x);
  // Prefer vertical stack when closer to top/bottom band
  if (v < h && v < 0.35) return y < 0.5 ? "top" : "bottom";
  if (h < 0.5) return x < 0.5 ? "left" : "right";
  return y < 0.5 ? "top" : "bottom";
}

function clearDropIndicators() {
  document.querySelectorAll(".playPanel.isDragOver, .playPanel.drop-top, .playPanel.drop-bottom, .playPanel.drop-left, .playPanel.drop-right")
    .forEach((p) => {
      p.classList.remove("isDragOver", "drop-top", "drop-bottom", "drop-left", "drop-right");
    });
}

/**
 * Move panel relative to another:
 * - left/right = same row, side-by-side
 * - top/bottom = stack **inside that column only** (map above narrator stays in the chat column)
 */
function placePlayPanel(fromId, toId, edge) {
  if (!fromId || !toId || fromId === toId) return;
  playLayout = normalizePlayLayout(playLayout);
  // Deep-clone cells (including stacks)
  const rows = playLayout.rows.map((r) => ({
    height: r.height,
    panels: r.panels.map((p) =>
      Array.isArray(p.stack)
        ? { width: p.width, stack: p.stack.map((s) => ({ id: s.id, height: s.height })) }
        : { id: p.id, width: p.width },
    ),
  }));

  const fromLoc = findPanelLocation(fromId, rows);
  const toLoc = findPanelLocation(toId, rows);
  if (!fromLoc || !toLoc) return;

  // Don't allow stacking a panel onto itself inside same stack
  if (
    fromLoc.row === toLoc.row &&
    fromLoc.col === toLoc.col &&
    fromLoc.stackIndex != null &&
    toLoc.stackIndex != null
  ) {
    // Reorder inside same stack
    const cell = rows[fromLoc.row].panels[fromLoc.col];
    if (Array.isArray(cell?.stack)) {
      const [leaf] = cell.stack.splice(fromLoc.stackIndex, 1);
      let insertAt = toLoc.stackIndex;
      if (fromLoc.stackIndex < toLoc.stackIndex) insertAt -= 1;
      if (edge === "bottom") insertAt += 1;
      cell.stack.splice(Math.max(0, Math.min(insertAt, cell.stack.length)), 0, leaf);
      const hNorm = normalizeLayoutWeights(
        cell.stack.map((s) => s.height || 50),
        cell.stack.length,
        16,
      );
      cell.stack.forEach((s, i) => {
        s.height = hNorm[i];
      });
      playLayout.rows = rows;
      playLayout.custom = true;
      markCustomPlayLayout();
      return;
    }
  }

  const moved = extractPanelFromRows(rows, fromLoc);
  if (!moved?.id) return;

  // Recompute target location after extraction
  let tLoc = findPanelLocation(toId, rows);
  if (!tLoc) {
    // Target vanished — put moved back on last row
    if (!rows.length) rows.push({ height: 100, panels: [] });
    rows[rows.length - 1].panels.push({ id: moved.id, width: moved.width || 12 });
    playLayout.rows = rows;
    playLayout.custom = true;
    markCustomPlayLayout();
    return;
  }

  // Drop empty rows after extract
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    if (!rows[i].panels.length) {
      rows.splice(i, 1);
      if (tLoc.row > i) tLoc = { ...tLoc, row: tLoc.row - 1 };
    }
  }
  tLoc = findPanelLocation(toId, rows);
  if (!tLoc) return;

  if (edge === "left" || edge === "right") {
    if (!rows[tLoc.row]) return;
    // If target is inside a stack, place beside the whole stack cell
    const insertAt = edge === "left" ? tLoc.col : tLoc.col + 1;
    const row = rows[tLoc.row];
    const share = Math.max(10, 100 / (row.panels.length + 1));
    row.panels.splice(Math.max(0, Math.min(insertAt, row.panels.length)), 0, {
      id: moved.id,
      width: share,
    });
    const norm = normalizeLayoutWeights(
      row.panels.map((p) => p.width),
      row.panels.length,
      8,
    );
    row.panels.forEach((p, i) => {
      p.width = norm[i];
    });
  } else {
    // Column-local stack: only above/below the target panel (not a full-width grid row)
    const cell = rows[tLoc.row].panels[tLoc.col];
    if (!cell) return;
    const leafMoved = { id: moved.id, height: 40 };
    if (Array.isArray(cell.stack) && cell.stack.length) {
      let insertAt = tLoc.stackIndex != null ? tLoc.stackIndex : 0;
      if (edge === "bottom") insertAt += 1;
      cell.stack.splice(Math.max(0, Math.min(insertAt, cell.stack.length)), 0, leafMoved);
      const hNorm = normalizeLayoutWeights(
        cell.stack.map((s) => s.height || 50),
        cell.stack.length,
        16,
      );
      cell.stack.forEach((s, i) => {
        s.height = hNorm[i];
      });
    } else {
      // Promote single panel cell into a stack
      const targetId = cell.id;
      const topFirst = edge === "top";
      cell.stack = topFirst
        ? [leafMoved, { id: targetId, height: 60 }]
        : [{ id: targetId, height: 60 }, leafMoved];
      delete cell.id;
      const hNorm = normalizeLayoutWeights(
        cell.stack.map((s) => s.height || 50),
        cell.stack.length,
        16,
      );
      cell.stack.forEach((s, i) => {
        s.height = hNorm[i];
      });
    }
  }

  playLayout.rows = rows;
  playLayout.custom = true;
  markCustomPlayLayout();
}

/**
 * Layout mode: sceneFocus = narration is the main stage; map is secondary.
 * Used on Continue/load and when reading/acting; map-primary is the idle travel view.
 * Skipped automatically when the player has a custom layout.
 */
function setSceneFocus(on, options = {}) {
  const enabled = Boolean(on);
  if (hasCustomPlayLayout() && !options.force) {
    // Custom layout is sticky — only soft UX (focus/scroll), never reflow columns.
    if (enabled && options.scroll !== false) {
      document.querySelector("#chatColumn")?.scrollIntoView({
        behavior: options.smooth === false ? "auto" : "smooth",
        block: "nearest",
      });
      latestOutput?.scrollTo?.({ top: 0, behavior: "smooth" });
    }
    if (enabled && options.focusInput) turnInput?.focus();
    return;
  }
  gameView?.classList.toggle("sceneFocus", enabled);
  gameView?.classList.toggle("mapPrimary", !enabled);
  // Refresh auto flex proportions when not using a sticky custom layout
  if (!hasCustomPlayLayout()) applyPlayLayout();
  const hint = document.querySelector("#chatIdleHint");
  if (hint && !gameView?.classList.contains("isGenerating") && !hasCustomPlayLayout()) {
    hint.textContent = enabled
      ? "Narration is main — Map for travel"
      : "Map is main while idle";
  }
  const sceneBtn = document.querySelector("#mapFocusChatBtn");
  const mapBtn = document.querySelector("#sceneFocusMapBtn");
  if (sceneBtn) sceneBtn.classList.toggle("activeChip", enabled);
  if (mapBtn) mapBtn.classList.toggle("activeChip", !enabled);
  if (enabled && options.scroll !== false) {
    document.querySelector("#chatColumn")?.scrollIntoView({ behavior: options.smooth === false ? "auto" : "smooth", block: "nearest" });
    latestOutput?.scrollTo?.({ top: 0, behavior: "smooth" });
  }
  if (enabled && options.focusInput) {
    turnInput?.focus();
  }
}

function setGeneratingUi(on) {
  gameView?.classList.toggle("isGenerating", Boolean(on));
  // Generating elevates the scene column only when layout is still automatic.
  if (on && !hasCustomPlayLayout()) setSceneFocus(true, { scroll: false, smooth: false });
  const hint = document.querySelector("#chatIdleHint");
  if (hint) {
    if (hasCustomPlayLayout()) {
      hint.textContent = on ? "Model working…" : "Custom layout (auto focus off)";
    } else {
      hint.textContent = on
        ? "Model working — narration focused"
        : gameView?.classList.contains("sceneFocus")
          ? "Narration is main — Map for travel"
          : "Map is main while idle";
    }
  }
}

function bindPlayLayoutControls() {
  if (playLayoutBound) return;
  playLayoutBound = true;
  const grid = document.querySelector("#playGrid");
  if (!grid) return;

  // Column + row + in-column stack resize
  grid.addEventListener("pointerdown", (event) => {
    const colSplit = event.target.closest(".playSplitterCol");
    const rowSplit = event.target.closest(".playSplitterRow");
    const stackSplit = event.target.closest(".playSplitterStack");
    if (!colSplit && !rowSplit && !stackSplit) return;
    if (!grid.contains(event.target)) return;
    event.preventDefault();

    // Ensure we have a mutable custom layout snapshot
    if (!playLayout.custom) {
      playLayout = normalizePlayLayout({
        custom: true,
        rows: activeLayoutRows().map((r) => ({
          height: r.height,
          panels: r.panels.map((p) =>
            Array.isArray(p.stack)
              ? { width: p.width, stack: p.stack.map((s) => ({ ...s })) }
              : { ...p },
          ),
        })),
      });
    }
    playLayout = normalizePlayLayout(playLayout);

    if (stackSplit) {
      const rowIndex = Number(stackSplit.dataset.rowIndex);
      const colIndex = Number(stackSplit.dataset.colIndex);
      const splitIndex = Number(stackSplit.dataset.stackSplitIndex);
      const cell = playLayout.rows[rowIndex]?.panels?.[colIndex];
      if (!cell || !Array.isArray(cell.stack) || !Number.isFinite(splitIndex)) return;
      const stackEl = stackSplit.closest(".playStack");
      const rect = (stackEl || grid).getBoundingClientRect();
      const startY = event.clientY;
      const startHeights = normalizeLayoutWeights(
        cell.stack.map((s) => s.height || 50),
        cell.stack.length,
        16,
      );
      stackSplit.classList.add("isDragging");
      document.body.style.cursor = "row-resize";
      document.body.style.userSelect = "none";
      const onMove = (ev) => {
        const deltaPct = ((ev.clientY - startY) / Math.max(1, rect.height)) * 100;
        const next = [...startHeights];
        next[splitIndex] = startHeights[splitIndex] + deltaPct;
        next[splitIndex + 1] = startHeights[splitIndex + 1] - deltaPct;
        const norm = normalizeLayoutWeights(next, next.length, 16);
        cell.stack.forEach((s, i) => {
          s.height = norm[i];
        });
        playLayout.custom = true;
        applyPlayLayout({ rebuild: false });
      };
      const onUp = () => {
        stackSplit.classList.remove("isDragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        savePlayLayoutState();
        updatePlayLayoutChrome();
        refreshLocalMap?.();
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      return;
    }

    if (colSplit) {
      const rowIndex = Number(colSplit.dataset.rowIndex);
      const index = Number(colSplit.dataset.splitIndex);
      const row = playLayout.rows[rowIndex];
      if (!row || !Number.isFinite(index)) return;
      const rowEl = colSplit.closest(".playRow");
      const rect = (rowEl || grid).getBoundingClientRect();
      const startX = event.clientX;
      const startWidths = normalizeLayoutWeights(
        row.panels.map((p) => p.width),
        row.panels.length,
        8,
      );
      colSplit.classList.add("isDragging");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      const onMove = (ev) => {
        const deltaPct = ((ev.clientX - startX) / Math.max(1, rect.width)) * 100;
        const next = [...startWidths];
        next[index] = startWidths[index] + deltaPct;
        next[index + 1] = startWidths[index + 1] - deltaPct;
        const norm = normalizeLayoutWeights(next, next.length, 8);
        row.panels.forEach((p, i) => {
          p.width = norm[i];
        });
        playLayout.custom = true;
        applyPlayLayout({ rebuild: false });
      };
      const onUp = () => {
        colSplit.classList.remove("isDragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        savePlayLayoutState();
        updatePlayLayoutChrome();
        refreshLocalMap?.();
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      return;
    }

    if (rowSplit) {
      const index = Number(rowSplit.dataset.rowSplitIndex);
      if (!Number.isFinite(index)) return;
      const rect = grid.getBoundingClientRect();
      const startY = event.clientY;
      const startHeights = normalizeLayoutWeights(
        playLayout.rows.map((r) => r.height),
        playLayout.rows.length,
        12,
      );
      rowSplit.classList.add("isDragging");
      document.body.style.cursor = "row-resize";
      document.body.style.userSelect = "none";
      const onMove = (ev) => {
        const deltaPct = ((ev.clientY - startY) / Math.max(1, rect.height)) * 100;
        const next = [...startHeights];
        next[index] = startHeights[index] + deltaPct;
        next[index + 1] = startHeights[index + 1] - deltaPct;
        const norm = normalizeLayoutWeights(next, next.length, 12);
        playLayout.rows.forEach((r, i) => {
          r.height = norm[i];
        });
        playLayout.custom = true;
        applyPlayLayout({ rebuild: false });
      };
      const onUp = () => {
        rowSplit.classList.remove("isDragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        savePlayLayoutState();
        updatePlayLayoutChrome();
        refreshLocalMap?.();
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    }
  });

  // Drag place via headers — top/bottom stacks, left/right beside
  let dragId = null;
  grid.addEventListener("pointerdown", (event) => {
    const header = event.target.closest("[data-play-drag]");
    if (!header || event.target.closest("button, select, input, a, textarea, label")) return;
    if (event.target.closest(".playSplitter")) return;
    const id = header.getAttribute("data-play-drag");
    if (!PLAY_PANEL_IDS.includes(id)) return;
    if (event.button != null && event.button !== 0) return;
    const panel = panelEl(id);
    if (!panel) return;
    dragId = id;
    const startX = event.clientX;
    const startY = event.clientY;
    let armed = false;
    let lastEdge = null;
    panel.classList.add("isDraggingPanel");

    const onMove = (ev) => {
      const dist = Math.hypot(ev.clientX - startX, ev.clientY - startY);
      if (!armed && dist < 6) return;
      armed = true;
      clearDropIndicators();
      const el = document.elementFromPoint(ev.clientX, ev.clientY);
      const over = el?.closest?.("[data-play-panel]");
      if (over && over.dataset.playPanel && over.dataset.playPanel !== dragId) {
        const edge = panelDropEdge(over, ev.clientX, ev.clientY);
        lastEdge = edge;
        over.classList.add("isDragOver", `drop-${edge}`);
      } else {
        lastEdge = null;
      }
    };
    const onUp = (ev) => {
      panel.classList.remove("isDraggingPanel");
      const edge = lastEdge;
      const overEl = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.("[data-play-panel]");
      const toId = overEl?.dataset?.playPanel;
      clearDropIndicators();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!armed) {
        dragId = null;
        return;
      }
      if (toId && dragId && toId !== dragId) {
        // Seed custom layout from current auto rows if needed
        if (!playLayout.custom) {
          playLayout = normalizePlayLayout({
            custom: true,
            rows: activeLayoutRows().map((r) => ({
              height: r.height,
              panels: r.panels.map((p) => ({ ...p })),
            })),
          });
        }
        placePlayPanel(dragId, toId, edge || panelDropEdge(overEl, ev.clientX, ev.clientY));
      }
      dragId = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });

  document.querySelector("#resetPlayLayoutBtn")?.addEventListener("click", () => {
    if (playLayout.custom) {
      if (window.confirm("Reset play layout to automatic scene/map focus?")) resetPlayLayout();
    } else {
      playLayout = normalizePlayLayout({
        custom: true,
        rows: activeLayoutRows().map((r) => ({
          height: r.height,
          panels: r.panels.map((p) => ({ ...p })),
        })),
      });
      savePlayLayoutState();
      applyPlayLayout();
      document.querySelector("#playLayoutHint")?.classList.remove("hidden");
    }
  });
  document.querySelector("#playLayoutHintReset")?.addEventListener("click", () => resetPlayLayout());

  grid.addEventListener("keydown", (event) => {
    const colSplit = event.target.closest(".playSplitterCol");
    const rowSplit = event.target.closest(".playSplitterRow");
    if (!colSplit && !rowSplit) return;
    if (!playLayout.custom) {
      playLayout = normalizePlayLayout({
        custom: true,
        rows: activeLayoutRows().map((r) => ({
          height: r.height,
          panels: r.panels.map((p) => ({ ...p })),
        })),
      });
    }
    const step = event.shiftKey ? 4 : 1.5;
    if (colSplit) {
      const rowIndex = Number(colSplit.dataset.rowIndex);
      const index = Number(colSplit.dataset.splitIndex);
      const row = playLayout.rows[rowIndex];
      if (!row) return;
      let delta = 0;
      if (event.key === "ArrowLeft") delta = -step;
      if (event.key === "ArrowRight") delta = step;
      if (!delta) return;
      event.preventDefault();
      const next = normalizeLayoutWeights(
        row.panels.map((p) => p.width),
        row.panels.length,
        8,
      );
      next[index] += delta;
      next[index + 1] -= delta;
      const norm = normalizeLayoutWeights(next, next.length, 8);
      row.panels.forEach((p, i) => {
        p.width = norm[i];
      });
      markCustomPlayLayout();
      return;
    }
    if (rowSplit) {
      const index = Number(rowSplit.dataset.rowSplitIndex);
      let delta = 0;
      if (event.key === "ArrowUp") delta = -step;
      if (event.key === "ArrowDown") delta = step;
      if (!delta) return;
      event.preventDefault();
      const next = normalizeLayoutWeights(
        playLayout.rows.map((r) => r.height),
        playLayout.rows.length,
        12,
      );
      next[index] += delta;
      next[index + 1] -= delta;
      const norm = normalizeLayoutWeights(next, next.length, 12);
      playLayout.rows.forEach((r, i) => {
        r.height = norm[i];
      });
      markCustomPlayLayout();
    }
  });
}

window.renderTabHtmlForPopout = function renderTabHtmlForPopout(tab) {
  if (tab === "imageStudio" || tab === "art") {
    try {
      return `<div class="popoutTabInner" data-popout-tab="imageStudio">${renderImageStudioHtml()}</div>`;
    } catch (error) {
      return `<p class="empty">${escapeHtml(error.message || String(error))}</p>`;
    }
  }
  if (tab === "imageBrowser" || tab === "iib") {
    try {
      return `<div class="popoutTabInner" data-popout-tab="imageBrowser">${renderImageBrowserShellHtml()}</div>`;
    } catch (error) {
      return `<p class="empty">${escapeHtml(error.message || String(error))}</p>`;
    }
  }
  const renderers = TAB_RENDERERS();
  const fn = renderers[tab];
  if (!fn) return `<p class="empty">Unknown tab.</p>`;
  try {
    return `<div class="popoutTabInner" data-popout-tab="${escapeHtml(tab)}">${fn()}</div>`;
  } catch (error) {
    return `<p class="empty">${escapeHtml(error.message || String(error))}</p>`;
  }
}

window.getUiTheme = function getUiTheme() {
  return document.documentElement.getAttribute("data-theme") || "dusk";
}

function markPoppedTabs() {
  if (!indexTabs) return;
  indexTabs.querySelectorAll("button[data-tab]").forEach((btn) => {
    const tab = btn.dataset.tab;
    const floated = Boolean(floatPanels[tab]);
    const windowed = popoutWindows[tab] && !popoutWindows[tab].closed;
    const popped = floated || windowed || poppedOutTabs.has(tab);
    btn.classList.toggle("isPopped", popped);
    const hint = btn.querySelector("[data-popout]");
    if (hint) {
      hint.title = floated ? "Focus floating panel" : "Float panel on this page (single monitor)";
    }
    const winHint = btn.querySelector("[data-popout-window]");
    if (winHint) {
      winHint.title = windowed ? "Focus external window" : "Open in a separate browser window";
    }
  });
}

function openTabWindow(tab) {
  const key = String(tab || "player");
  if (popoutWindows[key] && !popoutWindows[key].closed) {
    popoutWindows[key].focus();
    poppedOutTabs.add(key);
    markPoppedTabs();
    return popoutWindows[key];
  }
  const url = `/static/popout.html?tab=${encodeURIComponent(key)}`;
  const win = window.open(url, `morkyn-popout-${key}`, "width=720,height=900,menubar=no,toolbar=no,location=no,status=no");
  if (!win) {
    window.alert("External window blocked. Use ⧉ to float on this page instead.");
    return openTabFloat(key);
  }
  popoutWindows[key] = win;
  poppedOutTabs.add(key);
  markPoppedTabs();
  window.setTimeout(() => pushPopoutUpdate(key), 400);
  const poll = window.setInterval(() => {
    if (!popoutWindows[key] || popoutWindows[key].closed) {
      window.clearInterval(poll);
      delete popoutWindows[key];
      if (!floatPanels[key]) poppedOutTabs.delete(key);
      markPoppedTabs();
    }
  }, 1200);
  return win;
}

function defaultFloatPlacement(index = 0) {
  const offset = 20 + index * 36;
  return {
    left: Math.min(offset + 72, Math.max(24, window.innerWidth - 340)),
    top: Math.min(offset + 72, Math.max(48, window.innerHeight - 220)),
    width: 360,
    height: 420,
    collapsed: true,
    pinned: false,
  };
}

function floatPanelStoredSize(panel, key) {
  /** Prefer CSS vars / saved state — never chip offsetWidth when collapsed. */
  const st = floatWindowState[key] || {};
  const rawW = String(panel?.style?.getPropertyValue("--float-w") || "").replace("px", "").trim();
  const rawH = String(panel?.style?.getPropertyValue("--float-h") || "").replace("px", "").trim();
  let w = Number(rawW);
  let h = Number(rawH);
  if (!Number.isFinite(w) || w < 120) w = Number(st.width) || 360;
  if (!Number.isFinite(h) || h < 80) h = Number(st.height) || 420;
  // Only fall back to live box if expanded (not a chip)
  const chip =
    panel?.classList.contains("isCollapsed") && !panel?.classList.contains("isPinned");
  if (!chip && panel) {
    if (!Number.isFinite(w) || w < 120) w = panel.offsetWidth || 360;
    if (!Number.isFinite(h) || h < 80) h = panel.offsetHeight || 420;
  }
  const large = key === "imageBrowser" || key === "imageStudio";
  const maxW = large ? 1100 : 560;
  const maxH = large ? 900 : 680;
  return {
    width: Math.min(maxW, Math.max(260, Math.round(w))),
    height: Math.min(maxH, Math.max(180, Math.round(h))),
  };
}

function applyFloatPanelSize(panel, width, height) {
  if (!panel) return;
  const w = Math.max(260, Math.round(Number(width) || 360));
  const h = Math.max(180, Math.round(Number(height) || 420));
  panel.style.setProperty("--float-w", `${w}px`);
  panel.style.setProperty("--float-h", `${h}px`);
  // Keep inline sizes in sync for non-!important paths; collapsed chip ignores them via CSS.
  panel.style.width = `${w}px`;
  panel.style.height = `${h}px`;
}

function persistFloatPanel(key, panel) {
  if (!panel) return;
  const size = floatPanelStoredSize(panel, key);
  const left = Number.parseFloat(panel.style.left);
  const top = Number.parseFloat(panel.style.top);
  floatWindowState[key] = {
    open: true,
    left: Number.isFinite(left) ? left : panel.offsetLeft || 40,
    top: Number.isFinite(top) ? top : panel.offsetTop || 40,
    width: size.width,
    height: size.height,
    collapsed: panel.classList.contains("isCollapsed") && !panel.classList.contains("isPinned"),
    pinned: panel.classList.contains("isPinned"),
  };
  // Always write vars so collapse never “forgets” the real window size
  applyFloatPanelSize(panel, size.width, size.height);
  saveFloatWindowState();
}

function applyFloatPanelChrome(panel, key) {
  const st = floatWindowState[key] || defaultFloatPlacement(Object.keys(floatPanels).length);
  const size = floatPanelStoredSize(panel, key);
  applyFloatPanelSize(panel, size.width, size.height);
  panel.style.left = `${Math.max(0, Number(st.left) || 40)}px`;
  panel.style.top = `${Math.max(0, Number(st.top) || 40)}px`;
  const pinned = Boolean(st.pinned);
  const collapsed = pinned ? false : st.collapsed !== false;
  panel.classList.toggle("isPinned", pinned);
  panel.classList.toggle("isCollapsed", collapsed);
  const pinBtn = panel.querySelector("[data-float-pin]");
  const collapseBtn = panel.querySelector("[data-float-collapse]");
  if (pinBtn) {
    pinBtn.classList.toggle("activeChip", pinned);
    pinBtn.title = pinned ? "Unpin (return to hover-expand chip)" : "Pin open (stay expanded)";
  }
  if (collapseBtn) {
    collapseBtn.textContent = collapsed ? "▢" : "—";
    collapseBtn.title = collapsed ? "Collapsed — hover to expand, or click to pin open" : "Collapse to chip";
  }
}

function openTabFloat(tab, options = {}) {
  const key = String(tab || "player");
  const layer = getFloatLayer();
  if (!layer) return openTabWindow(key);
  if (floatPanels[key]) {
    const existing = floatPanels[key];
    // Re-parent if the panel was created under an old layer
    if (existing.parentElement !== layer) layer.appendChild(existing);
    raiseFloatPanel(existing);
    if (options.pinned) {
      existing.classList.add("isPinned");
      existing.classList.remove("isCollapsed");
      applyFloatPanelChrome(existing, key);
    } else {
      // Peek-expand on re-open click
      existing.classList.add("isHoverExpand");
      window.setTimeout(() => existing.classList.remove("isHoverExpand"), 1600);
    }
    return existing;
  }
  if (!floatWindowState[key] || options.forceDefaults) {
    floatWindowState[key] = defaultFloatPlacement(Object.keys(floatPanels).length);
    // Default: collapsed chip — callers like Image Library can force pin + size
    floatWindowState[key].collapsed = options.pinned ? false : true;
    floatWindowState[key].pinned = Boolean(options.pinned);
    if (options.width) floatWindowState[key].width = options.width;
    if (options.height) floatWindowState[key].height = options.height;
    if (options.left != null) floatWindowState[key].left = options.left;
    if (options.top != null) floatWindowState[key].top = options.top;
  }
  const panel = document.createElement("section");
  panel.className = options.pinned ? "floatPanel isPinned" : "floatPanel isCollapsed";
  panel.dataset.floatTab = key;
  panel.innerHTML = `
    <header class="floatPanelHeader" data-float-drag>
      <strong title="${escapeHtml(TAB_LABELS[key] || key)}">${escapeHtml(TAB_LABELS[key] || key)}</strong>
      <div class="floatPanelActions">
        <button type="button" class="chipBtn secondaryButton" data-float-collapse title="Collapse / expand">—</button>
        <button type="button" class="chipBtn secondaryButton" data-float-pin title="Pin open (stay expanded)">Pin</button>
        <button type="button" class="chipBtn secondaryButton" data-float-window title="Open as browser window">↗</button>
        <button type="button" class="chipBtn secondaryButton" data-float-close title="Close">×</button>
      </div>
    </header>
    <div class="floatPanelBody" data-float-body></div>
    <div class="floatResizeHandle floatResizeE" data-float-resize="x" title="Resize width"></div>
    <div class="floatResizeHandle floatResizeS" data-float-resize="y" title="Resize height"></div>
    <div class="floatResizeHandle floatResizeCorner" data-float-resize="both" title="Resize both"></div>
  `;
  const body = panel.querySelector("[data-float-body]");
  body.innerHTML = renderTabHtmlForPopout(key);
  decorateFunctionHelp(body);
  layer.appendChild(panel);
  floatPanels[key] = panel;
  poppedOutTabs.add(key);
  markPoppedTabs();
  applyFloatPanelChrome(panel, key);
  raiseFloatPanel(panel);

  panel.querySelector("[data-float-close]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    closeTabFloat(key);
  });
  panel.querySelector("[data-float-window]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    openTabWindow(key);
  });
  panel.querySelector("[data-float-pin]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    const pinned = !panel.classList.contains("isPinned");
    panel.classList.toggle("isPinned", pinned);
    if (pinned) panel.classList.remove("isCollapsed");
    else panel.classList.add("isCollapsed");
    floatWindowState[key] = {
      ...(floatWindowState[key] || {}),
      open: true,
      pinned,
      collapsed: !pinned,
    };
    applyFloatPanelChrome(panel, key);
    raiseFloatPanel(panel);
    persistFloatPanel(key, panel);
  });
  panel.querySelector("[data-float-collapse]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    // — toggles chip collapse only; never forces Pin (Pin is separate).
    if (panel.classList.contains("isCollapsed")) {
      panel.classList.remove("isCollapsed");
      // keep pin state as-is
    } else {
      panel.classList.add("isCollapsed");
      panel.classList.remove("isPinned"); // chip mode is unpinned
    }
    const pinned = panel.classList.contains("isPinned");
    const collapsed = panel.classList.contains("isCollapsed") && !pinned;
    floatWindowState[key] = {
      ...(floatWindowState[key] || {}),
      open: true,
      pinned,
      collapsed,
    };
    applyFloatPanelChrome(panel, key);
    raiseFloatPanel(panel);
    persistFloatPanel(key, panel);
  });
  // Click / drag / expand raises only this window above sibling floats
  panel.addEventListener("pointerdown", () => {
    raiseFloatPanel(panel);
  });
  // Keep expanded briefly after hover leave so user can move to buttons
  let leaveTimer = null;
  panel.addEventListener("mouseenter", () => {
    if (leaveTimer) window.clearTimeout(leaveTimer);
    panel.classList.add("isHoverExpand");
    // Soft raise on hover so you can dig under another open float
    raiseFloatPanel(panel);
  });
  panel.addEventListener("mouseleave", () => {
    leaveTimer = window.setTimeout(() => {
      panel.classList.remove("isHoverExpand");
    }, 220);
  });
  enableFloatDrag(panel, key);
  enableFloatResize(panel, key);
  persistFloatPanel(key, panel);
  return panel;
}

function closeTabFloat(tab) {
  const key = String(tab || "");
  const panel = floatPanels[key];
  if (panel) {
    if (floatWindowState[key]) {
      floatWindowState[key].open = false;
      saveFloatWindowState();
    }
    panel.remove();
    delete floatPanels[key];
  }
  if (!popoutWindows[key] || popoutWindows[key].closed) poppedOutTabs.delete(key);
  markPoppedTabs();
}

function enableFloatDrag(panel, key) {
  const handle = panel.querySelector("[data-float-drag]");
  if (!handle) return;
  let sx = 0;
  let sy = 0;
  let ox = 0;
  let oy = 0;
  let dragging = false;
  const onMove = (event) => {
    if (!dragging) return;
    const maxX = Math.max(8, window.innerWidth - 64);
    const maxY = Math.max(8, window.innerHeight - 40);
    const nx = Math.min(maxX, Math.max(0, ox + (event.clientX - sx)));
    const ny = Math.min(maxY, Math.max(0, oy + (event.clientY - sy)));
    panel.style.left = `${nx}px`;
    panel.style.top = `${ny}px`;
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    if (key) persistFloatPanel(key, panel);
  };
  handle.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) return;
    dragging = true;
    raiseFloatPanel(panel);
    sx = event.clientX;
    sy = event.clientY;
    // offsetLeft/Top are relative to offsetParent; prefer CSS left/top for fixed layer
    ox = Number.parseFloat(panel.style.left) || panel.offsetLeft || 0;
    oy = Number.parseFloat(panel.style.top) || panel.offsetTop || 0;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });
}

function enableFloatResize(panel, key) {
  const handles = panel.querySelectorAll("[data-float-resize]");
  if (!handles.length) return;
  let sx = 0;
  let sy = 0;
  let sw = 0;
  let sh = 0;
  let mode = "both"; // x | y | both
  let resizing = false;
  const onMove = (event) => {
    if (!resizing) return;
    const maxW = Math.min(window.innerWidth - 16, key === "imageBrowser" || key === "imageStudio" ? 1100 : 560);
    const maxH = Math.min(window.innerHeight - 16, key === "imageBrowser" || key === "imageStudio" ? 900 : 680);
    let w = sw;
    let h = sh;
    if (mode === "x" || mode === "both") {
      w = Math.min(maxW, Math.max(260, sw + (event.clientX - sx)));
    }
    if (mode === "y" || mode === "both") {
      h = Math.min(maxH, Math.max(180, sh + (event.clientY - sy)));
    }
    // Only update CSS vars + synced size — never let chip measurements win
    applyFloatPanelSize(panel, w, h);
  };
  const onUp = () => {
    if (!resizing) return;
    resizing = false;
    panel.classList.remove("resizing");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    if (key) persistFloatPanel(key, panel);
  };
  handles.forEach((handle) => {
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      // Ignore resize while chip-collapsed (handles should be hidden anyway)
      if (panel.classList.contains("isCollapsed") && !panel.classList.contains("isPinned")) {
        return;
      }
      mode = String(handle.getAttribute("data-float-resize") || "both").toLowerCase();
      if (mode !== "x" && mode !== "y") mode = "both";
      // Expand if needed, but NEVER force Pin — user can still minimize with —
      const size = floatPanelStoredSize(panel, key);
      applyFloatPanelSize(panel, size.width, size.height);
      const keepPinned = panel.classList.contains("isPinned");
      panel.classList.remove("isCollapsed");
      floatWindowState[key] = {
        ...(floatWindowState[key] || {}),
        open: true,
        pinned: keepPinned,
        collapsed: false,
        width: size.width,
        height: size.height,
      };
      raiseFloatPanel(panel);
      resizing = true;
      panel.classList.add("resizing");
      sx = event.clientX;
      sy = event.clientY;
      sw = size.width;
      sh = size.height;
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
  });
}

function restoreSavedFloatWindows() {
  const keys = Object.keys(floatWindowState || {});
  keys.forEach((key) => {
    // Only restore if previously open — marked by a sticky flag
    if (floatWindowState[key]?.open) openTabFloat(key);
  });
}

function openTabPopout(tab, mode = "float") {
  if (mode === "window") return openTabWindow(tab);
  return openTabFloat(tab);
}

function pushPopoutUpdate(tab) {
  const html = renderTabHtmlForPopout(tab);
  const win = popoutWindows[tab];
  if (win && !win.closed) {
    try {
      win.postMessage({ type: "morkyn-popout", tab, html, theme: getUiTheme() }, window.location.origin);
    } catch (_) {
      /* ignore */
    }
  }
  const panel = floatPanels[tab];
  if (panel) {
    const body = panel.querySelector("[data-float-body]");
    if (body) {
      body.innerHTML = html;
      decorateFunctionHelp(body);
    }
  }
}

function pushAllPopouts() {
  const keys = new Set([...Object.keys(popoutWindows), ...Object.keys(floatPanels)]);
  keys.forEach((tab) => pushPopoutUpdate(tab));
}

function renderIndex() {
  const renderers = TAB_RENDERERS();
  if (!renderers[activeTab]) activeTab = "player";
  // Keep category rail in sync without wiping buttons mid-render unless needed
  if (indexTabs && !indexTabs.querySelector(`button[data-tab="${activeTab}"]`)) {
    buildIndexTabButtons(categoryForTab(activeTab).id);
  }
  indexTabs?.querySelectorAll("button[data-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === activeTab);
  });
  document.querySelectorAll(".tabCategoryBtn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tabCategory === categoryForTab(activeTab).id);
  });
  const catSelect = document.querySelector("#tabCategorySelect");
  if (catSelect) catSelect.value = categoryForTab(activeTab).id;
  indexContent.innerHTML = renderers[activeTab]();
  decorateFunctionHelp(indexContent);
  markPoppedTabs();
  pushAllPopouts();
  // Re-apply Forge gate after player/art tab HTML rebuild
  syncForgeImageGateUi();
}

function showImageMissingModal(detail) {
  const missing = Array.isArray(detail?.missing) ? detail.missing : [];
  const subjectMissing = Array.isArray(detail?.subject_readiness?.missing)
    ? detail.subject_readiness.missing
    : [];
  const allMissing = missing.length ? missing : subjectMissing;
  const hints = Array.isArray(detail?.install_hints) ? detail.install_hints : [];
  const header =
    detail?.error ||
    detail?.detail ||
    (allMissing.length ? "Cannot generate yet — missing info:" : "Image backend is not ready.");
  const lines = allMissing.length
    ? allMissing.map((m) => `• ${m.title || m.code || "Issue"}${m.detail ? ` — ${m.detail}` : ""}`).join("\n")
    : "";
  const hintLines = hints.length
    ? "\n\nGuides:\n" + hints.map((h) => `• ${h.label || "Guide"}: ${h.url || ""}`).join("\n")
    : allMissing.some((m) => String(m.code || "").includes("backend") || String(m.code || "") === "backend_off")
      ? "\n\nOpen LLM Settings → Images to set provider, Forge/Comfy URL, and install roots (Allow search)."
      : "";
  const body = [header, lines].filter(Boolean).join("\n\n");
  window.alert(`${body}${hintLines}`);
}

function setPlayerArtStatus(text, { bad = false } = {}) {
  const el = document.querySelector("#playerArtStatus");
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.classList.toggle("bad", bad);
  el.textContent = text;
}

function setSetupArtStatus(text, { bad = false } = {}) {
  const el = document.querySelector("#portraitArtStatus");
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("bad");
    return;
  }
  el.hidden = false;
  el.classList.toggle("bad", bad);
  el.textContent = text;
}

/** Client-side checklist: enough identity / world / visibility for character art. */
function assessLocalArtReadiness(payload = {}, { subject = "player" } = {}) {
  const missing = [];
  const name = String(payload.name || "").trim();
  const knownAs = String(payload.known_as || "").trim();
  const title = String(payload.title || "").trim();
  const age = String(payload.age || "").trim();
  const sex = String(payload.sex || "").trim();
  const backstory = String(payload.backstory || "").trim();
  const worldStyle = String(payload.world_style || "").trim();
  const extra = String(payload.extra || "").trim();
  const observed = String(payload.observed_description || payload.visibility_note || "").trim();
  const backendOn = !!(imageConfig && imageConfig.enabled);

  if (!backendOn) {
    missing.push({
      code: "backend_off",
      title: "Image backend is off",
      detail: "Open LLM Settings → Images and set provider to Forge, ComfyUI, or Demo.",
    });
  }
  if (subject === "player") {
    if (!name && !knownAs) {
      missing.push({
        code: "name",
        title: "Name or Known As",
        detail: "Set a character name on the Identity step.",
      });
    }
    // Soft bar: sex, age, title, short backstory, OR world style is enough to start.
    // (Sex defaults to Unspecified — that alone should not brick Generate.)
    const bodyOk = !!(
      sex ||
      age ||
      title ||
      backstory.length >= 20 ||
      extra.length >= 8 ||
      worldStyle
    );
    if (!bodyOk) {
      missing.push({
        code: "appearance_cues",
        title: "Sex, Age, or World style",
        detail:
          "On Identity: set Sex (Female/Male/…) or Age (e.g. 24). Or open the World step and pick a world style. Optional: a short backstory helps looks.",
      });
    }
  } else {
    if (!name && !knownAs && !observed) {
      missing.push({
        code: "subject",
        title: "Who is being drawn",
        detail: "Need a name or an observed description of what the player sees.",
      });
    }
    if (!observed && !sex && !age && backstory.length < 24) {
      missing.push({
        code: "observed",
        title: "Nothing observed to draw",
        detail: "Wait until the player sees them (e.g. a figure in a drain through a wall).",
      });
    }
  }

  return {
    ok: missing.length === 0,
    can_generate: missing.length === 0,
    missing,
    message:
      missing.length === 0
        ? "Ready to generate."
        : "Need more info: " + missing.map((m) => m.detail || m.title).join(" "),
  };
}

function formatArtReadinessMessage(gate) {
  if (!gate) return "";
  if (gate.can_generate || gate.ok) {
    const mode = gate.visibility_mode;
    if (mode === "partial") {
      return `Ready — partial view only (${gate.visibility_note || "glimpse"}).`;
    }
    return gate.message || "Ready to generate face + full body.";
  }
  // Prefer actionable detail over short titles like "Appearance cues".
  const first = (gate.missing || [])[0];
  if (first?.detail) return `Blocked: ${first.detail}`;
  const bits = (gate.missing || []).map((m) => m.title || m.code).filter(Boolean);
  return bits.length ? `Blocked: ${bits.join(" · ")}` : gate.message || "Not ready.";
}

async function regeneratePlayerPortrait(kindOrKinds = "both") {
  const localGate = assessLocalArtReadiness(
    {
      name: state?.player?.name || "",
      known_as: state?.player?.public_name || "",
      age: state?.player?.age || "",
      sex: state?.player?.sex || "",
      backstory: state?.player?.backstory || "",
      world_style: state?.settings?.playthrough_options?.world_style || "",
    },
    { subject: "player" },
  );
  if (!localGate.can_generate) {
    setPlayerArtStatus(formatArtReadinessMessage(localGate), { bad: true });
    showImageMissingModal(localGate);
    return;
  }
  let kinds = ["face", "fullbody"];
  const raw = String(kindOrKinds || "both").toLowerCase();
  if (raw === "face") kinds = ["face"];
  else if (raw === "fullbody" || raw === "body") kinds = ["fullbody"];
  else if (raw === "both") kinds = ["face", "fullbody"];

  return enqueueGpuTask(async () => {
    const faceFrame = document.querySelector("#playerFaceFrame");
    const bodyFrame = document.querySelector("#playerFullbodyFrame");
    if (kinds.includes("face") && faceFrame) {
      faceFrame.innerHTML = `<div class="npcPortraitPlaceholder"><span>Face…</span><small>starting</small></div>`;
    }
    if (kinds.includes("fullbody") && bodyFrame) {
      bodyFrame.innerHTML = `<div class="npcPortraitPlaceholder"><span>Body…</span><small>${kinds.includes("face") ? "after face" : "ref face"}</small></div>`;
    }
    setPlayerArtStatus("Hook Forge/Comfy if running; start only if offline…");
    try {
      const faceRef = playerFaceUrl() || "";
      const res = await fetch("/api/image/character-set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_state: true,
          kinds,
          launch_if_offline: true,
          persist: true,
          subject: "player",
          use_face_reference: true,
          reference_data_url: kinds.includes("fullbody") && !kinds.includes("face") ? faceRef : "",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail && typeof data.detail === "object" ? data.detail : { error: data.detail || data.error || "Character art failed" };
        showImageMissingModal(detail);
        throw new Error(typeof detail.error === "string" ? detail.error : "Character art failed");
      }
      const faceUrl = data.face?.data_url || "";
      const bodyUrl = data.fullbody?.data_url || "";
      if (faceUrl) {
        localStorage.setItem("morkyn-player-portrait", faceUrl);
        localStorage.setItem("morkyn-player-portrait-sig", playerPortraitSignature());
        if (state) state.player_portrait = { data_url: faceUrl, kind: "face", equipment: data.equipment_used || [] };
        pushStudioCandidate("face", data.face);
      }
      if (bodyUrl) {
        localStorage.setItem("morkyn-player-fullbody", bodyUrl);
        if (state) state.player_fullbody = { data_url: bodyUrl, kind: "fullbody", equipment: data.equipment_used || [] };
        pushStudioCandidate("fullbody", data.fullbody);
      }
      const ref = data.fullbody?.used_face_reference ? " · face ref" : "";
      setPlayerArtStatus(`Done (${Math.round((data.elapsed_ms || 0) / 1000)}s) — ${kinds.join(" + ")}${ref}.`);
      renderIndex();
    } catch (error) {
      setPlayerArtStatus(error.message || String(error), { bad: true });
      if (faceFrame && kinds.includes("face") && !playerFaceUrl()) {
        faceFrame.innerHTML = `<div class="npcPortraitPlaceholder"><span>${escapeHtml(error.message || String(error))}</span><small>Images settings</small></div>`;
      }
      if (bodyFrame && kinds.includes("fullbody") && !playerFullbodyUrl()) {
        bodyFrame.innerHTML = `<div class="npcPortraitPlaceholder"><span>Failed</span><small>See alert / status</small></div>`;
      }
    }
  }, "Generating character art…");
}

async function loadBible() {
  const response = await fetch("/api/bible");
  if (!response.ok) throw new Error(await response.text());
  bible = await response.json();
  renderIndex();
}

async function loadModelConfig() {
  const response = await fetch("/api/model-config");
  if (!response.ok) throw new Error(await response.text());
  modelConfig = await response.json();
  renderIndex();
}

async function loadImageConfig() {
  const response = await fetch("/api/image-config");
  if (!response.ok) throw new Error(await response.text());
  imageConfig = await response.json();
  syncPortraitControls();
  return imageConfig;
}

async function openModelModal(options = {}) {
  if (!modelModal || !modelModalContent) return;
  if (options.imageTab) {
    imageSettingsTab = String(options.imageTab);
  }
  modelModalContent.innerHTML = paragraphs("Loading model settings...");
  const response = await fetch("/api/model-config");
  if (!response.ok) throw new Error(await response.text());
  modelConfig = await response.json();
  try {
    await loadImageConfig();
  } catch (_) {
    imageConfig = imageConfig || { provider: "off" };
  }
  try {
    await loadImageCatalog(imageConfig?.provider);
  } catch (_) {
    imageCatalog = imageCatalog || {};
  }
  modelModalContent.innerHTML = renderModelForm();
  decorateFunctionHelp(modelModalContent);
  // Install checklist loads when Images section is shown (roots may be empty).
  refreshImageInstallablesPanel(modelModalContent).catch(() => {});
}

async function openImageSettingsModal(tab = "installs") {
  imageSettingsTab = tab || "installs";
  await openModelModalFromUi();
  // ensure installs tab after re-render
  if (modelModalContent) {
    imageSettingsTab = tab || "installs";
    modelModalContent.querySelectorAll(".imageSettingsTab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.imageTab === imageSettingsTab);
    });
    modelModalContent.querySelectorAll(".imageTabPanel").forEach((panel) => {
      panel.classList.toggle("open", panel.dataset.imagePanel === imageSettingsTab);
    });
    await refreshImageInstallablesPanel(modelModalContent);
  }
}

const SETUP_ART_COLLAPSE_KEY = "morkyn-setup-art-collapsed";

function setupArtIsCollapsed() {
  try {
    const v = localStorage.getItem(SETUP_ART_COLLAPSE_KEY);
    // Default: collapsed when unset
    return v !== "0";
  } catch (_) {
    return true;
  }
}

function applySetupArtCollapsed(collapsed, { persist = true } = {}) {
  const card = document.querySelector("#characterPortraitCard");
  if (!card) return;
  const body = card.querySelector("#setupArtBody") || document.querySelector("#setupArtBody");
  const btn = card.querySelector("#setupArtCollapseBtn") || document.querySelector("#setupArtCollapseBtn");
  const meta = card.querySelector("#setupArtCollapseMeta") || document.querySelector("#setupArtCollapseMeta");
  const next = !!collapsed;
  card.classList.toggle("isCollapsed", next);
  // Prefer class-driven visibility; keep hidden attr in sync for a11y
  if (body) {
    if (next) body.setAttribute("hidden", "");
    else body.removeAttribute("hidden");
    // Belt-and-suspenders for stubborn UA/CSS
    body.style.display = next ? "none" : "";
  }
  if (btn) btn.setAttribute("aria-expanded", next ? "false" : "true");
  if (meta) {
    meta.textContent = next
      ? "Collapsed · click to expand art tools"
      : "Expanded · library · face / body";
  }
  if (persist) {
    try {
      localStorage.setItem(SETUP_ART_COLLAPSE_KEY, next ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
  }
  // Opening Character art: show simple guide + probe Forge (Studio/Library only if online).
  if (!next) {
    showSetupArtGuide({ force: false });
    probeImageBackendStatus({ silent: true })
      .then(() => {
        if (isImageBackendConnected()) {
          // Optional: do not auto-open library; user opens when ready
        }
      })
      .catch(() => {});
  }
}

function toggleSetupArtCollapsed() {
  const card = document.querySelector("#characterPortraitCard");
  if (!card) return;
  const collapsed = card.classList.contains("isCollapsed");
  applySetupArtCollapsed(!collapsed);
}

function forgeRootLooksSet() {
  const root = String(imageConfig?.forge_root || pendingImageRoots?.forge || "").trim();
  return root.length > 2;
}

function initSetupArtCollapse(options = {}) {
  const { forceCollapsed = false } = options;
  const card = document.querySelector("#characterPortraitCard");
  if (!card) return;

  // Bind once via delegation on the card (survives re-renders of children better)
  if (card.dataset.collapseBound !== "1") {
    card.dataset.collapseBound = "1";
    card.addEventListener("click", (event) => {
      const t = event.target;
      if (!(t instanceof Element)) return;
      // Forge install button — open settings, do not toggle
      if (t.closest("#setupArtOpenImageSettings")) {
        event.preventDefault();
        event.stopPropagation();
        openImageSettingsModal("installs").catch((error) => {
          window.alert(error.message || String(error));
        });
        return;
      }
      // Expand/collapse: header toggle, chevron, title, or whole head bar
      if (
        t.closest("#setupArtCollapseBtn") ||
        t.closest("[data-art-expand]") ||
        (t.closest(".characterArtHead") && !t.closest("button.secondaryButton"))
      ) {
        event.preventDefault();
        event.stopPropagation();
        toggleSetupArtCollapsed();
      }
    });
  }

  // New games always start collapsed. Otherwise respect last expand preference
  // (default collapsed when unset). Never auto-expand just because Forge root is set.
  const collapsed = forceCollapsed ? true : setupArtIsCollapsed();
  applySetupArtCollapsed(collapsed, { persist: forceCollapsed });
}

async function applySessionThemeModelFromForm(form) {
  const input = form?.querySelector("[data-session-theme-model], input[name='session_theme_model']");
  const themeModel = String(input?.value || "").trim().slice(0, 120);
  // Always keep setup-side draft so Start carries the override.
  if (!lastSessionTheme || typeof lastSessionTheme !== "object") {
    lastSessionTheme = themeModel ? { theme_model: themeModel } : null;
  } else {
    lastSessionTheme = { ...lastSessionTheme, theme_model: themeModel };
  }
  // Mid-run: persist into playthrough_options.session_theme
  if (state?.setup_complete) {
    const response = await fetch("/api/session-theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme_model: themeModel }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || "Could not apply session theme model.");
    }
    const payload = await response.json();
    if (state.settings && typeof state.settings === "object") {
      const opts = state.settings.playthrough_options && typeof state.settings.playthrough_options === "object"
        ? { ...state.settings.playthrough_options }
        : {};
      opts.session_theme = payload.session_theme || { ...(opts.session_theme || {}), theme_model: themeModel };
      state.settings = { ...state.settings, playthrough_options: opts };
    }
    lastSessionTheme = payload.session_theme || lastSessionTheme;
    return payload;
  }
  return { theme_model: themeModel, setup_only: true };
}

async function saveModelConfig(form) {
  const payload = modelPayloadFromForm(form);
  const response = await fetch("/api/model-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  modelConfig = await response.json();
  let sessionNote = "";
  try {
    const applied = await applySessionThemeModelFromForm(form);
    sessionNote = applied?.setup_only
      ? " Session theme model stored for Start."
      : ` Session theme model: ${applied?.theme_model ? applied.theme_model : "(cleared)"}.`;
  } catch (error) {
    sessionNote = ` Session theme model not applied: ${error.message || error}`;
  }
  if (activeTab === "model" && !gameView.classList.contains("hidden")) renderIndex();
  if (modelModalContent && modelModalToggle?.checked) {
    modelModalContent.innerHTML = `${renderModelForm()}<p class="good">Model settings saved.${escapeHtml(sessionNote)}</p>`;
    decorateFunctionHelp(modelModalContent);
  }
  latestOutput.innerHTML = paragraphs(`Model settings saved.${sessionNote}`);
}

function modelPayloadFromForm(form) {
  const formData = new FormData(form);
  const preset = String(formData.get("api_preset") || "xai");
  const presetDefaults = {
    xai: { api_base_url: "https://api.x.ai/v1", api_model: "grok-4.5" },
    openai: { api_base_url: "https://api.openai.com/v1", api_model: "gpt-4.1-mini" },
    custom: { api_base_url: "http://127.0.0.1:4000/v1", api_model: "local-agent" },
  };
  const defaults = presetDefaults[preset] || presetDefaults.xai;
  let apiBase = String(formData.get("api_base_url") || "").trim();
  let apiModel = String(formData.get("api_model") || "").trim();
  // When user switches preset, empty-ish fields can adopt preset defaults client-side.
  if (!apiBase) apiBase = defaults.api_base_url;
  if (!apiModel) apiModel = defaults.api_model;
  const theme_adapter_map = {};
  form.querySelectorAll("[data-theme-adapter-hint]").forEach((input) => {
    const hint = String(input.getAttribute("data-theme-adapter-hint") || "").trim();
    if (!hint) return;
    theme_adapter_map[hint] = String(input.value || "").trim();
  });
  return {
    provider: formData.get("provider") || "llama_cpp",
    gguf_model_path: formData.get("gguf_model_path"),
    llama_cpp_base_url: formData.get("llama_cpp_base_url"),
    ollama_model: formData.get("ollama_model") || "llama3.1",
    ollama_base_url: formData.get("ollama_base_url") || "http://localhost:11434",
    api_preset: preset,
    api_base_url: apiBase,
    api_model: apiModel,
    api_key: String(formData.get("api_key") || "").trim(),
    response_token_cap: Math.round(finiteNumber(formData.get("response_token_cap"), 1500)),
    response_token_hard_cap: Math.round(finiteNumber(formData.get("response_token_hard_cap"), 2000)),
    theme_adapter_map,
  };
}

function _lastFilledInput(form, name, fallback = "") {
  const vals = [...(form?.querySelectorAll?.(`input[name="${name}"]`) || [])]
    .map((el) => String(el.value || "").trim().replace(/^["']|["']$/g, ""))
    .filter(Boolean);
  // Last non-empty wins (Installs tab fields come after Forge/Comfy tabs in the form).
  return vals.length ? vals[vals.length - 1] : String(fallback || "").trim();
}

function imagePayloadFromForm(form) {
  const formData = new FormData(form);
  const forgeCkCustom = String(formData.get("forge_checkpoint_custom") || "").trim();
  const comfyCkCustom = String(formData.get("comfy_checkpoint_custom") || "").trim();
  const forgeCheckpoint = forgeCkCustom || String(formData.get("forge_checkpoint") || "").trim();
  const comfyCheckpoint = comfyCkCustom || String(formData.get("comfy_checkpoint") || "").trim();
  // Custom paste fields always win so users can use any installed sampler/VAE/upscaler
  const forgeVae =
    String(formData.get("forge_vae_custom") || "").trim() ||
    String(formData.get("forge_vae") || "").trim();
  const forgeSampler =
    String(formData.get("forge_sampler_custom") || "").trim() ||
    String(formData.get("forge_sampler") || "Euler a").trim() ||
    "Euler a";
  const forgeScheduler =
    String(formData.get("forge_scheduler_custom") || "").trim() ||
    String(formData.get("forge_scheduler") || "Automatic").trim() ||
    "Automatic";
  const forgeHrUpscaler =
    String(formData.get("forge_hr_upscaler_custom") || "").trim() ||
    String(formData.get("forge_hr_upscaler") || "Latent").trim() ||
    "Latent";
  const forgeRoot = _lastFilledInput(form, "forge_root", pendingImageRoots.forge || "");
  const comfyRoot = _lastFilledInput(form, "comfy_root", pendingImageRoots.comfyui || "");
  if (forgeRoot) pendingImageRoots.forge = forgeRoot;
  if (comfyRoot) pendingImageRoots.comfyui = comfyRoot;
  return {
    provider: String(formData.get("provider") || "off"),
    forge_base_url: String(formData.get("forge_base_url") || "http://127.0.0.1:7860").trim(),
    comfy_base_url: String(formData.get("comfy_base_url") || "http://127.0.0.1:8188").trim(),
    comfy_checkpoint: comfyCheckpoint,
    comfy_workflow: String(formData.get("comfy_workflow") || "txt2img_api.json").trim(),
    portrait_style: String(formData.get("portrait_style") || "").trim(),
    negative_prompt: String(formData.get("negative_prompt") || "").trim(),
    default_width: Math.round(finiteNumber(formData.get("default_width"), 512)),
    default_height: Math.round(finiteNumber(formData.get("default_height"), 512)),
    default_steps: Math.round(finiteNumber(formData.get("default_steps"), 20)),
    default_cfg: finiteNumber(formData.get("default_cfg"), 7),
    timeout_seconds: Math.round(finiteNumber(formData.get("timeout_seconds"), 180)),
    forge_root: forgeRoot,
    comfy_root: comfyRoot,
    auto_launch_if_offline: !!form.querySelector('input[name="auto_launch_if_offline"]')?.checked,
    auto_generate_npc_portraits: !!form.querySelector('input[name="auto_generate_npc_portraits"]')?.checked,
    character_consistency: String(formData.get("character_consistency") || "light").trim() || "light",
    character_lock_weight: finiteNumber(formData.get("character_lock_weight"), 0.65),
    fullbody_ref_denoise: finiteNumber(formData.get("fullbody_ref_denoise"), 0.80),
    fullbody_use_face_ref: String(formData.get("character_consistency") || "light") !== "off",
    adetailer_enable: !!form.querySelector('input[name="adetailer_enable"]')?.checked,
    adetailer_use_face_ref: !!form.querySelector('input[name="adetailer_use_face_ref"]')?.checked,
    adetailer_on_face: !!form.querySelector('input[name="adetailer_on_face"]')?.checked,
    adetailer_on_fullbody: !!form.querySelector('input[name="adetailer_on_fullbody"]')?.checked,
    adetailer_model: String(formData.get("adetailer_model") || "face_yolov8n.pt").trim() || "face_yolov8n.pt",
    adetailer_denoise: finiteNumber(formData.get("adetailer_denoise"), 0.4),
    forge_checkpoint: forgeCheckpoint,
    forge_vae: forgeVae,
    forge_sampler: forgeSampler,
    forge_scheduler: forgeScheduler,
    forge_clip_skip: Math.round(finiteNumber(formData.get("forge_clip_skip"), 1)),
    forge_restore_faces: !!form.querySelector('input[name="forge_restore_faces"]')?.checked,
    forge_tiling: !!form.querySelector('input[name="forge_tiling"]')?.checked,
    forge_enable_hr: !!form.querySelector('input[name="forge_enable_hr"]')?.checked,
    forge_hr_scale: finiteNumber(formData.get("forge_hr_scale"), 1.5),
    forge_hr_upscaler: forgeHrUpscaler,
    forge_denoising_strength: finiteNumber(formData.get("forge_denoising_strength"), 0.45),
    iib_open_mode: String(formData.get("iib_open_mode") || "embed").trim() || "embed",
    iib_base_url: String(formData.get("iib_base_url") || "").trim(),
    comfy_sampler_name: String(formData.get("comfy_sampler_name") || "euler").trim(),
    comfy_scheduler: String(formData.get("comfy_scheduler") || "normal").trim(),
  };
}

async function loadImageCatalog(provider) {
  const prov = provider || imageConfig?.provider || "off";
  const response = await fetch("/api/image-catalog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: prov === "off" ? "" : prov }),
  });
  imageCatalog = await response.json().catch(() => ({}));
  return imageCatalog;
}

async function saveImageConfig(form, options = {}) {
  const { rerender = false, statusMessage = "" } = options;
  // Capture roots from the live form into pending before any re-render.
  if (form) {
    const fr = form.querySelector('input[name="forge_root"]')?.value;
    const cr = form.querySelector('input[name="comfy_root"]')?.value;
    if (fr != null && String(fr).trim()) pendingImageRoots.forge = String(fr).trim();
    if (cr != null && String(cr).trim()) pendingImageRoots.comfyui = String(cr).trim();
  }
  const payload = form ? imagePayloadFromForm(form) : { ...(imageConfig || {}), ...pendingImageRoots && {
    forge_root: pendingImageRoots.forge || imageConfig?.forge_root || "",
    comfy_root: pendingImageRoots.comfyui || imageConfig?.comfy_root || "",
  } };
  // Always prefer pending roots if set (survives re-render races).
  if (pendingImageRoots.forge) payload.forge_root = pendingImageRoots.forge;
  if (pendingImageRoots.comfyui) payload.comfy_root = pendingImageRoots.comfyui;
  const response = await fetch("/api/image-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  imageConfig = await response.json();
  if (imageConfig.forge_root) pendingImageRoots.forge = imageConfig.forge_root;
  if (imageConfig.comfy_root) pendingImageRoots.comfyui = imageConfig.comfy_root;
  syncPortraitControls();
  // Only full re-render when explicitly requested (Save button). Intermediate
  // Test/Launch/Readiness must NOT wipe the form or the path looks "reset".
  if (rerender && modelModalContent && modelModalToggle?.checked) {
    modelModalContent.innerHTML = `${renderModelForm()}${statusMessage ? `<p class="good">${escapeHtml(statusMessage)}</p>` : `<p class="good">Image settings saved.</p>`}`;
    decorateFunctionHelp(modelModalContent);
    refreshImageInstallablesPanel(modelModalContent).catch(() => {});
  }
  return imageConfig;
}

async function testCharacterLockStack(statusEl) {
  const el =
    statusEl ||
    document.querySelector("[data-character-lock-status]") ||
    document.querySelector("#setupArtLockStatus");
  if (el) {
    el.hidden = false;
    el.classList.remove("bad", "good");
    el.textContent = "Probing Forge for InstantID / FaceID / ReActor…";
  }
  try {
    const res = await fetch("/api/image/character-lock-test", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || "Probe failed");
    const p = data.probe || {};
    const r = data.resolved || {};
    const mode = r.mode || p.recommended_mode || "light";
    const okLight = p.api_ok && (mode === "light" || mode === "off" || !r.use_strong);
    const okStrong = !!p.strong_ready && !!r.use_strong;
    const lines = [
      data.message || p.message || "",
      `Mode: ${mode}${r.use_strong ? " (ControlNet)" : mode === "off" ? "" : " (img2img ref)"} · API ${
        p.api_ok ? "up" : "down"
      } · ControlNet ${p.controlnet ? "yes" : "no"}`,
    ];
    // One optional footnote max (avoid repeating InstantID three times).
    const hints = data.install_hints || p.install_hints || [];
    if (!okStrong && Array.isArray(hints) && hints[0]?.detail) {
      const d = String(hints[0].detail);
      const main = String(data.message || p.message || "");
      if (d && !main.includes(d.slice(0, 40))) {
        lines.push(`Note: ${d}`);
      }
    }
    if (el) {
      // Light + API up is success (recommended), not a red failure.
      el.classList.remove("bad", "good");
      if (!p.api_ok && String(p.provider || "") === "forge") el.classList.add("bad");
      else if (okLight || okStrong) el.classList.add("good");
      el.textContent = lines.filter(Boolean).join("\n");
      el.style.whiteSpace = "pre-wrap";
    }
    return data;
  } catch (err) {
    if (el) {
      el.classList.add("bad");
      el.textContent = err.message || String(err);
    }
    throw err;
  }
}

async function testImageConnection(container) {
  const status = container.querySelector("[data-image-status]");
  const form = container.querySelector("#imageForm") || document.querySelector("#imageForm");
  if (status) status.innerHTML = `<p class="empty">Saving image settings and probing backend…</p>`;
  if (form) {
    await saveImageConfig(form, { rerender: false });
  }
  const response = await fetch("/api/image-status", { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok && !payload.message) throw new Error(await response.text());
  const ok = !!payload.ok;
  const msg = escapeHtml(payload.message || (ok ? "OK" : "Failed"));
  if (status) {
    status.innerHTML = ok
      ? `<p class="good">${msg}</p>`
      : `<p class="bad">${msg}</p>`;
  }
  forgeImageStatus = {
    ok,
    provider: payload.provider || imageConfig?.provider || "off",
    message: payload.message || (ok ? "Image API online" : "Image API offline"),
    raw: payload,
  };
  syncForgeImageGateUi();
  return payload;
}

function syncPortraitControls() {
  const payload = setupPortraitPayloadFromForm();
  const gate = assessLocalArtReadiness(payload, { subject: "player" });
  const preview = document.querySelector("#portraitPreviewBtn");
  const ready = !!gate.can_generate;
  if (preview) {
    // Keep the button clickable even when blocked so we can explain why
    // (native disabled swallows clicks → felt like "Generate does nothing").
    preview.disabled = false;
    preview.setAttribute("aria-disabled", ready ? "false" : "true");
    preview.classList.toggle("isBlocked", !ready);
    preview.title = ready
      ? "Generate face + full-body via local Forge/ComfyUI"
      : formatArtReadinessMessage(gate);
  }
  setSetupArtStatus(formatArtReadinessMessage(gate), { bad: !ready });
  // In-game player art button (when present).
  const inGame = document.querySelector("#playerPortraitRegen, [data-player-portrait-regen]");
  if (inGame && state?.player) {
    const playGate = assessLocalArtReadiness(
      {
        name: state.player.name || "",
        known_as: state.player.public_name || "",
        age: state.player.age || "",
        sex: state.player.sex || "",
        backstory: state.player.backstory || "",
        world_style: state.settings?.playthrough_options?.world_style || "",
      },
      { subject: "player" },
    );
    inGame.classList.toggle("isBlocked", !playGate.can_generate);
    inGame.title = playGate.can_generate
      ? "Generate face + full body from player identity, gear, injuries"
      : formatArtReadinessMessage(playGate);
  }
}

/** Session art studio candidates (face/body drafts). */
const imageStudioCandidates = [];
let setupArtLoraCatalog = [];

/** Last Forge/Comfy image-status probe (ok = API reachable). */
let forgeImageStatus = null;
const ART_GUIDE_KEY = "morkyn-art-guide-v1";

function hasSeenArtGuide() {
  try {
    return localStorage.getItem(ART_GUIDE_KEY) === "1";
  } catch {
    return false;
  }
}

function markArtGuideSeen() {
  try {
    localStorage.setItem(ART_GUIDE_KEY, "1");
  } catch {
    /* ignore */
  }
}

function isImageBackendConnected() {
  const provider = String(imageConfig?.provider || forgeImageStatus?.provider || "").toLowerCase();
  if (provider !== "forge" && provider !== "comfyui") return false;
  return !!(forgeImageStatus && forgeImageStatus.ok);
}

async function probeImageBackendStatus({ silent = true } = {}) {
  const wasOnline = !!(forgeImageStatus && forgeImageStatus.ok);
  try {
    if (!imageConfig) {
      try {
        await loadImageConfig();
      } catch (_) {
        imageConfig = imageConfig || { provider: "off", enabled: false };
      }
    }
    const provider = String(imageConfig?.provider || "off").toLowerCase();
    if (provider !== "forge" && provider !== "comfyui") {
      forgeImageStatus = {
        ok: false,
        provider,
        message: "Image backend is Off — set provider to ForgeSD in Images settings.",
      };
      syncForgeImageGateUi();
      return forgeImageStatus;
    }
    const response = await fetch("/api/image-status", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    forgeImageStatus = {
      ok: !!payload.ok,
      provider: payload.provider || provider,
      message: payload.message || (payload.ok ? "Image API online" : "Image API offline"),
      raw: payload,
    };
  } catch (err) {
    forgeImageStatus = {
      ok: false,
      provider: imageConfig?.provider || "off",
      message: err?.message || String(err),
    };
  }
  syncForgeImageGateUi();
  // When Forge/Comfy just came online, pull full sampler/VAE/upscaler lists automatically
  if (forgeImageStatus?.ok && !wasOnline) {
    const needCatalog =
      !imageCatalog?.forge?.samplers?.length ||
      !imageCatalog?.forge?.upscalers?.length ||
      !imageCatalog?.forge?.vaes?.length ||
      !imageCatalog?.ok;
    if (needCatalog) {
      const prov = String(forgeImageStatus.provider || imageConfig?.provider || "forge");
      loadImageCatalog(prov)
        .then(() => {
          // Refresh open Images settings form if present
          if (modelModalContent?.querySelector?.("#imageForm") && modelModalToggle?.checked) {
            const status = modelModalContent.querySelector("[data-image-status]");
            modelModalContent.innerHTML = `${renderModelForm()}${
              status
                ? ""
                : `<p class="good">Catalog refreshed from connected backend (${imageCatalog?.forge?.samplers?.length || 0} samplers, ${imageCatalog?.forge?.vaes?.length || 0} VAEs, ${imageCatalog?.forge?.upscalers?.length || 0} upscalers).</p>`
            }`;
            decorateFunctionHelp(modelModalContent);
            refreshImageInstallablesPanel(modelModalContent).catch(() => {});
          }
          // Keep setup art checkpoint/lora lists in sync too
          if (typeof fillSetupArtCheckpointSelect === "function" && imageCatalog) {
            fillSetupArtCheckpointSelect(imageCatalog);
            setupArtLoraCatalog = imageCatalog?.forge?.loras || setupArtLoraCatalog || [];
            if (typeof renderSetupLoraList === "function") {
              renderSetupLoraList(document.querySelector("#setupArtLoraFilter")?.value || "");
            }
          }
        })
        .catch(() => {});
    }
  }
  if (!silent) {
    setSetupArtStatus?.(
      forgeImageStatus.message || (forgeImageStatus.ok ? "Forge online" : "Forge offline"),
      { bad: !forgeImageStatus.ok },
    );
  }
  return forgeImageStatus;
}

function syncForgeImageGateUi() {
  const online = isImageBackendConnected();
  const provider = String(imageConfig?.provider || forgeImageStatus?.provider || "off");
  const label =
    provider === "forge"
      ? "ForgeSD"
      : provider === "comfyui"
        ? "ComfyUI"
        : "Image backend";

  // Always show Studio/Library once provider is forge/comfyui — unlock when API ok.
  // (Previously parent .forgeImageLocked { display:none } could stick after re-renders.)
  document.querySelectorAll("[data-requires-forge-image]").forEach((el) => {
    el.hidden = false;
    el.removeAttribute("hidden");
    el.setAttribute("aria-hidden", "false");
    el.classList.toggle("isBlocked", !online);
    el.classList.toggle("isForgeOnline", online);
    if (online) {
      el.removeAttribute("disabled");
      el.title = el.getAttribute("data-title-online") || el.title || "";
    } else {
      el.removeAttribute("disabled"); // still clickable → probe / open settings
      if (!el.dataset.titleOfflineSaved) {
        el.dataset.titleOfflineSaved = el.title || "";
      }
      el.title = "Connect ForgeSD first (click to open image settings / re-check)";
    }
  });

  document.querySelectorAll(".artKindActions, .npcStageActions, .setupArtControls").forEach((row) => {
    row.classList.toggle("forgeImageUnlocked", online);
    row.classList.remove("forgeImageLocked"); // never use parent display:none lock
  });

  const status = document.querySelector("#setupArtForgeStatus");
  if (status) {
    status.classList.toggle("isOnline", online);
    status.classList.toggle("isOffline", !online);
    status.textContent = online
      ? `${label}: connected — Studio & Image Library ready.`
      : `${label}: not connected — Studio/Library stay available but will prompt you to connect.`;
  }

  const hint = document.querySelector("#setupArtForgeGateHint");
  if (hint) {
    hint.classList.toggle("isReady", online);
    hint.innerHTML = online
      ? `Forge is online. <strong>Studio</strong> = edit gens & candidates · <strong>Image Library ⧉</strong> = browse/pick/delete (movable window).`
      : `Set provider to <strong>ForgeSD</strong> and start the API (Test Connection). Buttons stay visible — click Studio/Library to re-check.`;
  }

  // Close floats if backend drops offline
  if (!online) {
    if (floatPanels.imageBrowser) closeTabFloat("imageBrowser");
    if (floatPanels.imageStudio) closeTabFloat("imageStudio");
  }
}

/** Periodic re-probe so Studio/Library unlock when Forge finishes booting. */
let _forgeGatePollTimer = null;
function startForgeImageGatePoll() {
  if (_forgeGatePollTimer) return;
  _forgeGatePollTimer = window.setInterval(() => {
    const prov = String(imageConfig?.provider || "").toLowerCase();
    if (prov !== "forge" && prov !== "comfyui") return;
    if (document.hidden) return;
    probeImageBackendStatus({ silent: true }).catch(() => {});
  }, 12000);
}

function showSetupArtGuide({ force = false } = {}) {
  const guide = document.querySelector("#setupArtGuide");
  if (!guide) return;
  if (!force && hasSeenArtGuide()) {
    guide.hidden = true;
    return;
  }
  guide.hidden = false;
  probeImageBackendStatus({ silent: true }).catch(() => {});
}

function dismissSetupArtGuide() {
  markArtGuideSeen();
  const guide = document.querySelector("#setupArtGuide");
  if (guide) guide.hidden = true;
}

function requireImageBackendConnected(actionLabel = "This tool") {
  if (isImageBackendConnected()) return true;
  const msg = `${actionLabel} unlocks after ForgeSD (or Comfy) is connected. Open “Set or install ForgeSD”, set the root/URL, Test Connection, then try again.`;
  setSetupArtStatus?.(msg, { bad: true });
  window.alert(msg);
  openImageSettingsModal("installs").catch(() => openModelModalFromUi?.());
  return false;
}
let lastSetupFaceDataUrl = "";
let lastSetupBodyDataUrl = "";
/** Active character-art backend tab: forge | comfyui */
let setupArtBackendTab = "forge";

function collectSetupLoras() {
  const list = document.querySelector("#setupArtLoraList");
  if (!list) return [];
  return [...list.querySelectorAll("input[data-lora-name]:checked")].map((el) => {
    const name = el.getAttribute("data-lora-name") || "";
    const weightEl = [...list.querySelectorAll("input[data-lora-weight]")].find(
      (w) => w.getAttribute("data-lora-weight") === name,
    );
    const weight = parseFloat(weightEl?.value || "1") || 1;
    return { name, weight };
  }).filter((x) => x.name);
}

/** Apply a data/portraits file into face or fullbody slots (setup + play). */
async function applyNativePortraitToSlot(name, slot = "face") {
  const id = String(name || "").trim();
  if (!id) return;
  const url = `/api/portraits/file?name=${encodeURIComponent(id)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Could not load portrait file");
    const blob = await res.blob();
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Read failed"));
      reader.readAsDataURL(blob);
    });
    if (!dataUrl.startsWith("data:")) throw new Error("Invalid image data");
    const asFace = slot !== "fullbody" && slot !== "body";
    if (asFace) {
      lastSetupFaceDataUrl = dataUrl;
      try {
        localStorage.setItem("morkyn-player-portrait", dataUrl);
      } catch (_) {
        /* ignore */
      }
      if (state) {
        state.player_portrait = { ...(state.player_portrait || {}), data_url: dataUrl };
      }
      const setupFace = document.querySelector("[data-setup-face]");
      if (setupFace) {
        setArtFrameContent(setupFace, {
          badge: "face",
          slot: "face",
          hasArt: true,
          html: `<img class="portraitImage" src="${dataUrl}" alt="Character face" draggable="true" />`,
        });
      }
      const playFace = document.querySelector("#playerFaceFrame");
      if (playFace) {
        setArtFrameContent(playFace, {
          slot: "player-face",
          hasArt: true,
          html: `${artClearButtonHtml("player-face")}<img src="${dataUrl}" alt="Player face" draggable="true" />`,
        });
      }
      setSetupArtStatus?.(`Applied ${id} as face.`);
    } else {
      lastSetupBodyDataUrl = dataUrl;
      try {
        localStorage.setItem("morkyn-player-fullbody", dataUrl);
      } catch (_) {
        /* ignore */
      }
      if (state) {
        state.player_fullbody = { ...(state.player_fullbody || {}), data_url: dataUrl };
      }
      const setupBody = document.querySelector("[data-setup-fullbody]");
      if (setupBody) {
        setArtFrameContent(setupBody, {
          badge: "body · 3:4",
          slot: "fullbody",
          hasArt: true,
          html: `<img class="portraitImage portraitImageFull" src="${dataUrl}" alt="Character full body" draggable="true" />`,
        });
      }
      const playBody = document.querySelector("#playerFullbodyFrame");
      if (playBody) {
        setArtFrameContent(playBody, {
          slot: "player-fullbody",
          hasArt: true,
          html: `${artClearButtonHtml("player-fullbody")}<img src="${dataUrl}" alt="Player full body" draggable="true" />`,
        });
      }
      setSetupArtStatus?.(`Applied ${id} as full body.`);
    }
    try {
      if (typeof renderPlayer === "function" && document.querySelector("#playerPanel, [data-tab='player']")) {
        /* player tab may re-render on next tick */
      }
    } catch (_) {
      /* ignore */
    }
  } catch (err) {
    setSetupArtStatus?.(err?.message || String(err) || "Apply failed", { bad: true });
  }
}

function updateSetupLoraSummary() {
  const meta = document.querySelector("#setupArtLoraSummary");
  if (!meta) return;
  const selected = collectSetupLoras();
  if (!selected.length) {
    const total = (setupArtLoraCatalog || []).length;
    meta.textContent = total
      ? `None selected · ${total} available — click to browse`
      : "None selected · click to browse";
    return;
  }
  const labels = selected.map((l) => {
    const short = l.name.length > 28 ? `${l.name.slice(0, 26)}…` : l.name;
    return `${short}:${Number(l.weight).toFixed(2).replace(/\.?0+$/, "") || "1"}`;
  });
  const shown = labels.slice(0, 3).join(", ");
  const more = labels.length > 3 ? ` +${labels.length - 3} more` : "";
  meta.textContent = `${selected.length} selected · ${shown}${more}`;
}

function renderSetupLoraList(filter = "") {
  const host = document.querySelector("#setupArtLoraList");
  if (!host) return;
  const q = String(filter || "").toLowerCase().trim();
  const selected = new Map(collectSetupLoras().map((l) => [l.name, l.weight]));
  const items = (setupArtLoraCatalog || [])
    .filter((l) => {
      const name = String(l.name || l.alias || "");
      return !q || name.toLowerCase().includes(q);
    })
    .slice(0, 120);
  if (!items.length) {
    const emptyMsg =
      setupArtBackendTab === "comfyui"
        ? "ComfyUI LoRA list is limited here — wire LoRAs in your workflow, or use ForgeSD for extra-network style picks."
        : setupArtLoraCatalog.length
          ? "No LoRAs match filter."
          : "No LoRAs loaded — start Forge and expand this dropdown (or open Studio).";
    host.innerHTML = `<span class="empty">${emptyMsg}</span>`;
    updateSetupLoraSummary();
    return;
  }
  host.innerHTML = items
    .map((l) => {
      const name = String(l.name || l.alias || "");
      const checked = selected.has(name) ? "checked" : "";
      const weight = selected.get(name) ?? 1;
      const short = name.length > 52 ? `${name.slice(0, 50)}…` : name;
      return `<label><input type="checkbox" data-lora-name="${escapeHtml(name)}" ${checked} /><span title="${escapeHtml(name)}">${escapeHtml(short)}</span><input class="loraWeight" type="number" min="0.05" max="2" step="0.05" value="${weight}" data-lora-weight="${escapeHtml(name)}" title="Weight" /></label>`;
    })
    .join("");
  updateSetupLoraSummary();
}

function fillSetupArtCheckpointSelect(data) {
  const ckpt = document.querySelector("#setupArtCheckpoint");
  if (!ckpt) return;
  const tab = setupArtBackendTab === "comfyui" ? "comfyui" : "forge";
  let models = [];
  if (tab === "comfyui") {
    models = data?.comfyui?.checkpoints || data?.comfyui?.disk_models || data?.disk_checkpoints || [];
  } else {
    models = data?.forge?.models || data?.disk_checkpoints || [];
  }
  const titles = dedupeCheckpointTitles(models);
  const current =
    ckpt.value ||
    (tab === "comfyui" ? imageConfig?.comfy_checkpoint : imageConfig?.forge_checkpoint) ||
    "";
  const currentKey = normalizeCheckpointKey(current);
  const opts = [`<option value="">Default / current</option>`].concat(
    titles.slice(0, 120).map((title) => {
      const sel =
        title === current || normalizeCheckpointKey(title) === currentKey ? "selected" : "";
      return `<option value="${escapeHtml(title)}" ${sel}>${escapeHtml(title)}</option>`;
    }),
  );
  // Preserve a saved checkpoint that isn't in the list yet
  if (current && !titles.some((t) => t === current || normalizeCheckpointKey(t) === currentKey)) {
    opts.splice(1, 0, `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)} (saved)</option>`);
  }
  ckpt.innerHTML = opts.join("");
}

function setSetupArtBackendTab(tab) {
  const next = tab === "comfyui" ? "comfyui" : "forge";
  setupArtBackendTab = next;
  document.querySelectorAll("[data-art-backend]").forEach((btn) => {
    const on = btn.getAttribute("data-art-backend") === next;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const hint = document.querySelector("#setupArtBackendHint");
  const loraHint = document.querySelector("#setupArtLoraHint");
  if (hint) {
    hint.textContent =
      next === "comfyui"
        ? "ComfyUI catalog · less verified path"
        : "Forge catalog · primary path";
  }
  if (loraHint) {
    loraHint.textContent =
      next === "comfyui"
        ? "ComfyUI — extra networks UI is Forge-first; workflow LoRAs preferred"
        : "Forge style — check to enable, set weight like A1111";
  }
  if (imageCatalog) {
    fillSetupArtCheckpointSelect(imageCatalog);
    if (next === "forge") {
      setupArtLoraCatalog = imageCatalog?.forge?.loras || setupArtLoraCatalog || [];
    } else {
      // Comfy catalog usually has no /loras list; keep empty unless API later adds it
      setupArtLoraCatalog = imageCatalog?.comfyui?.loras || [];
    }
    renderSetupLoraList(document.querySelector("#setupArtLoraFilter")?.value || "");
  }
  try {
    localStorage.setItem("morkyn-setup-art-backend", next);
  } catch (_) {
    /* ignore */
  }
}

async function refreshSetupArtCatalog() {
  try {
    if (!imageConfig) await loadImageConfig();
    // Fetch catalog for the tab in focus (and also fall back to config provider)
    const provider =
      setupArtBackendTab === "comfyui"
        ? "comfyui"
        : imageConfig?.provider === "comfyui"
          ? "forge"
          : imageConfig?.provider === "forge"
            ? "forge"
            : "forge";
    const res = await fetch("/api/image-catalog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider }),
    });
    const data = await res.json().catch(() => ({}));
    // Also pull the other backend lightly so both tabs have lists when possible
    let other = null;
    const otherProvider = provider === "comfyui" ? "forge" : "comfyui";
    try {
      const res2 = await fetch("/api/image-catalog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: otherProvider }),
      });
      other = await res2.json().catch(() => null);
    } catch (_) {
      other = null;
    }
    if (other && typeof other === "object") {
      if (provider === "forge") {
        data.comfyui = { ...(data.comfyui || {}), ...(other.comfyui || {}) };
      } else {
        data.forge = { ...(data.forge || {}), ...(other.forge || {}) };
      }
      if (!data.disk_checkpoints?.length && other.disk_checkpoints?.length) {
        data.disk_checkpoints = other.disk_checkpoints;
      }
    }
    imageCatalog = data;
    fillSetupArtCheckpointSelect(data);
    setupArtLoraCatalog =
      setupArtBackendTab === "comfyui"
        ? data?.comfyui?.loras || []
        : data?.forge?.loras || [];
    renderSetupLoraList(document.querySelector("#setupArtLoraFilter")?.value || "");
  } catch (_) {
    /* catalog optional */
  }
}

/** Track whether the player hand-edited engine prompt fields (don't clobber on auto-rebuild). */
const enginePromptDirty = {
  face: false,
  fullbody: false,
  face_negative: false,
  fullbody_negative: false,
};

let activeArtPromptTab = "face";

function setArtPromptTab(tab) {
  const next = tab === "fullbody" ? "fullbody" : "face";
  activeArtPromptTab = next;
  document.querySelectorAll("[data-art-prompt-tab]").forEach((btn) => {
    const on = btn.getAttribute("data-art-prompt-tab") === next;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("[data-art-prompt-panel]").forEach((panel) => {
    const on = panel.getAttribute("data-art-prompt-panel") === next;
    panel.classList.toggle("open", on);
    if (on) panel.removeAttribute("hidden");
    else panel.setAttribute("hidden", "");
  });
  // Highlight the matching preview frame
  document.querySelectorAll("[data-setup-face], [data-setup-fullbody]").forEach((el) => {
    el.classList.remove("artPromptSelected");
  });
  const frame =
    next === "fullbody"
      ? document.querySelector("[data-setup-fullbody]")
      : document.querySelector("[data-setup-face]");
  frame?.classList.add("artPromptSelected");
}

function setupPortraitPayloadFromForm(kinds = ["face", "fullbody"]) {
  const form = document.querySelector("#setupForm");
  if (!form) return {};
  const fd = new FormData(form);
  const worldStyles = [...form.querySelectorAll('input[name="world_style"]:checked')]
    .map((el) => el.value)
    .filter((v) => v && v !== "custom");
  let worldStyle = worldStyles.join(", ");
  if (!worldStyle) {
    try {
      worldStyle = String(readSetupValue(fd, "world_style") || fd.get("world_style") || "").trim();
    } catch (_) {
      worldStyle = String(fd.get("world_style") || "").trim();
    }
  }
  const age = String(fd.get("player_age") || "").trim();
  let sex = "";
  try {
    sex = String(readSetupValue(fd, "player_sex") || "").trim();
  } catch (_) {
    sex = String(fd.get("player_sex") || "").trim();
  }
  const artExtra = String(document.querySelector("#setupArtExtra")?.value || "").trim();
  const hair = String(fd.get("hair") || "").trim();
  const facialFeatures = String(fd.get("facial_features") || "").trim();
  const appearance = String(fd.get("appearance") || "").trim();
  const starterEquipment = String(fd.get("starter_equipment") || "")
    .split(/[,;|]+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .slice(0, 14);
  // Optional studio free-text only — hair/face/clothes go in dedicated fields
  const extra = artExtra;
  const facePrompt = String(document.querySelector("#setupArtFacePrompt")?.value || "").trim();
  const bodyPrompt = String(document.querySelector("#setupArtBodyPrompt")?.value || "").trim();
  const faceNegative = String(document.querySelector("#setupArtFaceNegative")?.value || "").trim();
  const bodyNegative = String(document.querySelector("#setupArtBodyNegative")?.value || "").trim();
  const checkpoint = String(document.querySelector("#setupArtCheckpoint")?.value || "").trim();
  const useFaceRef = document.querySelector("#setupArtUseFaceRef")?.checked !== false;
  const kindList = Array.isArray(kinds) ? kinds : [kinds];
  const normalized = [];
  for (const k of kindList) {
    const low = String(k || "").toLowerCase();
    if (low === "both") {
      normalized.push("face", "fullbody");
    } else if (low === "face" || low === "fullbody") {
      if (!normalized.includes(low)) normalized.push(low);
    }
  }
  if (!normalized.length) normalized.push("face", "fullbody");
  const faceUrl =
    lastSetupFaceDataUrl ||
    document.querySelector("[data-setup-face] img.portraitImage")?.src ||
    document.querySelector("[data-setup-face] img")?.src ||
    "";
  const bodyUrl =
    lastSetupBodyDataUrl ||
    document.querySelector("[data-setup-fullbody] img.portraitImage")?.src ||
    document.querySelector("[data-setup-fullbody] img")?.src ||
    "";
  // Whichever sibling already exists becomes the reference for the image being generated.
  let reference_data_url = "";
  if (normalized.length === 1 && useFaceRef) {
    if (normalized[0] === "fullbody" && faceUrl && faceUrl.startsWith("data:")) {
      reference_data_url = faceUrl;
    } else if (normalized[0] === "face" && bodyUrl && bodyUrl.startsWith("data:")) {
      reference_data_url = bodyUrl;
    }
  }
  return {
    name: String(fd.get("player_name") || "").trim(),
    title: String(fd.get("player_title") || "").trim(),
    known_as: String(fd.get("player_public_name") || "").trim(),
    backstory: String(fd.get("character_backstory") || "").trim(),
    world_style: worldStyle,
    location: String(fd.get("start_location") || "").trim(),
    age,
    sex,
    hair,
    facial_features: facialFeatures,
    appearance,
    equipment: starterEquipment,
    extra,
    face_prompt: facePrompt,
    fullbody_prompt: bodyPrompt,
    face_negative: faceNegative,
    fullbody_negative: bodyNegative,
    // Prefer per-image negatives; only fall back when both empty
    negative_override: faceNegative || bodyNegative || "",
    kinds: normalized,
    loras: collectSetupLoras(),
    use_face_reference: useFaceRef,
    reference_data_url,
    // Hook existing API first; only then start one backend if truly offline.
    launch_if_offline: true,
    persist: false,
    subject: "player",
    // Soft: if checkpoint selected, client also patches config before generate.
    _checkpoint: checkpoint,
  };
}

/** Turn FastAPI/Pydantic 422 detail into a short readable string. */
function formatApiValidationError(detail, fallback = "Request failed validation") {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const loc = Array.isArray(e?.loc) ? e.loc.filter((x) => x !== "body").join(".") : "";
        const msg = e?.msg || e?.message || "invalid";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean)
      .join("; ") || fallback;
  }
  if (typeof detail === "object") {
    if (detail.error) return String(detail.error);
    if (detail.message) return String(detail.message);
  }
  try {
    return JSON.stringify(detail);
  } catch (_) {
    return fallback;
  }
}

/**
 * Rebuild engine prompt textareas from identity + settings.
 * Does not mutate name/sex/backstory/etc. force=true overwrites dirty fields.
 */
async function rebuildEnginePrompts({ force = false, silent = false } = {}) {
  const payload = setupPortraitPayloadFromForm(
    document.querySelector("#setupArtGenKind")?.value || "both",
  );
  delete payload._checkpoint;
  // Preview assembly should not send empty overrides back into itself.
  const body = {
    name: payload.name,
    title: payload.title,
    known_as: payload.known_as,
    backstory: payload.backstory,
    world_style: payload.world_style,
    location: payload.location,
    age: payload.age,
    sex: payload.sex,
    extra: payload.extra,
    hair: payload.hair,
    facial_features: payload.facial_features,
    appearance: payload.appearance,
    equipment: payload.equipment,
    kinds: ["face", "fullbody"],
    loras: payload.loras,
    negative_override: force ? "" : "",
    subject: "player",
  };
  try {
    const res = await fetch("/api/image/character-prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || "Could not build prompts");
    const faceEl = document.querySelector("#setupArtFacePrompt");
    const bodyEl = document.querySelector("#setupArtBodyPrompt");
    const faceNegEl = document.querySelector("#setupArtFaceNegative");
    const bodyNegEl = document.querySelector("#setupArtBodyNegative");
    if (faceEl && (force || !enginePromptDirty.face || !faceEl.value.trim())) {
      faceEl.value = data.face_prompt || "";
      enginePromptDirty.face = false;
      faceEl.classList.remove("enginePromptDirty");
    }
    if (bodyEl && (force || !enginePromptDirty.fullbody || !bodyEl.value.trim())) {
      bodyEl.value = data.fullbody_prompt || "";
      enginePromptDirty.fullbody = false;
      bodyEl.classList.remove("enginePromptDirty");
    }
    if (faceNegEl && (force || !enginePromptDirty.face_negative || !faceNegEl.value.trim())) {
      faceNegEl.value = data.face_negative || data.negative || "";
      enginePromptDirty.face_negative = false;
      faceNegEl.classList.remove("enginePromptDirty");
    }
    if (bodyNegEl && (force || !enginePromptDirty.fullbody_negative || !bodyNegEl.value.trim())) {
      bodyNegEl.value = data.fullbody_negative || data.negative || "";
      enginePromptDirty.fullbody_negative = false;
      bodyNegEl.classList.remove("enginePromptDirty");
    }
    if (!silent) {
      setSetupArtStatus(
        "Engine prompts rebuilt (face + body, each with positive & negative). Select a tab to edit.",
      );
    }
    return data;
  } catch (err) {
    if (!silent) setSetupArtStatus(err.message || String(err), { bad: true });
    return null;
  }
}

function markEnginePromptDirty(kind) {
  const key =
    kind === "body"
      ? "fullbody"
      : kind === "negative"
        ? "face_negative"
        : kind;
  if (!key || !(key in enginePromptDirty)) return;
  enginePromptDirty[key] = true;
  const el =
    key === "face"
      ? document.querySelector("#setupArtFacePrompt")
      : key === "fullbody"
        ? document.querySelector("#setupArtBodyPrompt")
        : key === "face_negative"
          ? document.querySelector("#setupArtFaceNegative")
          : document.querySelector("#setupArtBodyNegative");
  el?.classList.add("enginePromptDirty");
}

function pushStudioCandidate(kind, resultPart, meta = {}) {
  if (!resultPart?.data_url) return;
  imageStudioCandidates.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    kind,
    data_url: resultPart.data_url,
    seed: resultPart.seed,
    prompt: resultPart.built_prompt || resultPart.prompt || "",
    used_face_reference: !!resultPart.used_face_reference,
    at: new Date().toISOString(),
    ...meta,
  });
  if (imageStudioCandidates.length > 40) imageStudioCandidates.length = 40;
  try {
    sessionStorage.setItem("morkyn-art-candidates", JSON.stringify(imageStudioCandidates.slice(0, 12).map((c) => ({
      id: c.id, kind: c.kind, data_url: c.data_url, seed: c.seed, at: c.at,
    }))));
  } catch (_) {
    /* quota */
  }
  renderImageStudioCandidates();
}

function artClearButtonHtml(slot) {
  return `<button type="button" class="artClearBtn" data-art-clear="${escapeHtml(slot)}" title="Remove image" aria-label="Remove image">×</button>`;
}

function setArtFrameContent(frame, { badge = "", html = "", hasArt = false, slot = "" } = {}) {
  if (!frame) return;
  const badgeHtml = badge ? `<span class="visionBadge">${escapeHtml(badge)}</span>` : "";
  const clear = hasArt && slot ? artClearButtonHtml(slot) : "";
  frame.innerHTML = `${badgeHtml}${clear}${html}`;
  frame.classList.toggle("hasArt", !!hasArt);
}

function setupFacePlaceholderHtml() {
  return `<div class="visionPlaceholder"><strong>Face</strong>Bust · drop image or generate</div>`;
}

function setupBodyPlaceholderHtml() {
  return `<div class="visionPlaceholder"><strong>Full body</strong>Drop image or generate (face ref when available)</div>`;
}

function applySetupArtResult(result, kinds) {
  const card = document.querySelector("#characterPortraitCard");
  const faceFrame = card?.querySelector("[data-setup-face]");
  const bodyFrame = card?.querySelector("[data-setup-fullbody]");
  const faceUrl = result.face?.data_url || "";
  const bodyUrl = result.fullbody?.data_url || "";
  if (faceUrl) {
    lastSetupFaceDataUrl = faceUrl;
    pushStudioCandidate("face", result.face);
    setArtFrameContent(faceFrame, {
      badge: "face",
      slot: "face",
      hasArt: true,
      html: `<img class="portraitImage" src="${faceUrl}" alt="Character face" draggable="true" />`,
    });
  }
  if (bodyUrl) {
    lastSetupBodyDataUrl = bodyUrl;
    pushStudioCandidate("fullbody", result.fullbody);
    setArtFrameContent(bodyFrame, {
      badge: "body · 3:4",
      slot: "fullbody",
      hasArt: true,
      html: `<img class="portraitImage portraitImageFull" src="${bodyUrl}" alt="Character full body" draggable="true" />`,
    });
  } else if (bodyFrame && kinds.includes("fullbody") && !bodyUrl && result.visibility_mode === "partial") {
    setArtFrameContent(bodyFrame, {
      badge: "partial",
      hasArt: false,
      html: `<div class="visionPlaceholder"><strong>Glimpse only</strong>Full body skipped.</div>`,
    });
  }
}

function clearArtSlot(slot) {
  const key = String(slot || "").toLowerCase();
  if (key === "face" || key === "setup-face") {
    lastSetupFaceDataUrl = "";
    try {
      localStorage.removeItem("morkyn-player-portrait");
      localStorage.removeItem("morkyn-player-portrait-sig");
    } catch (_) {
      /* ignore */
    }
    if (state) state.player_portrait = null;
    setArtFrameContent(document.querySelector("[data-setup-face]"), {
      badge: "face",
      hasArt: false,
      html: setupFacePlaceholderHtml(),
    });
    const pf = document.querySelector("#playerFaceFrame");
    if (pf) {
      setArtFrameContent(pf, {
        hasArt: false,
        html: `<div class="npcPortraitPlaceholder"><span>Face</span><small>drop / gen</small></div>`,
      });
    }
    setSetupArtStatus("Face image removed.");
    return;
  }
  if (key === "fullbody" || key === "setup-fullbody" || key === "body") {
    lastSetupBodyDataUrl = "";
    try {
      localStorage.removeItem("morkyn-player-fullbody");
    } catch (_) {
      /* ignore */
    }
    if (state) state.player_fullbody = null;
    setArtFrameContent(document.querySelector("[data-setup-fullbody]"), {
      badge: "body · 3:4",
      hasArt: false,
      html: setupBodyPlaceholderHtml(),
    });
    const pb = document.querySelector("#playerFullbodyFrame");
    if (pb) {
      setArtFrameContent(pb, {
        hasArt: false,
        html: `<div class="npcPortraitPlaceholder"><span>Full body</span><small>drop / gen</small></div>`,
      });
    }
    setSetupArtStatus("Full body image removed.");
    return;
  }
  if (key === "player-face") {
    clearArtSlot("face");
    setPlayerArtStatus("Face image removed.");
    return;
  }
  if (key === "player-fullbody") {
    clearArtSlot("fullbody");
    setPlayerArtStatus("Full body image removed.");
    return;
  }
  if (key === "npc") {
    const npcKey =
      focusedNpcCode || document.querySelector("#npcPortraitFrame")?.getAttribute("data-npc-key") || "";
    if (npcKey) {
      delete npcPortraitCache[npcKey];
      try {
        const stored = JSON.parse(localStorage.getItem("morkyn-npc-portraits") || "{}");
        delete stored[npcKey];
        localStorage.setItem("morkyn-npc-portraits", JSON.stringify(stored));
      } catch (_) {
        /* ignore */
      }
    }
    const frame = document.querySelector("#npcPortraitFrame");
    if (frame) {
      setArtFrameContent(frame, {
        hasArt: false,
        html: `<div class="npcPortraitPlaceholder"><span>${escapeHtml((npcKey || "?").slice(0, 1).toUpperCase())}</span><br/><small>drop / gen</small></div>`,
      });
      frame.setAttribute("data-art-slot", "npc");
      if (npcKey) frame.setAttribute("data-npc-key", npcKey);
    }
  }
}

async function generateSetupPortrait(kindOrKinds = "both") {
  const payload = setupPortraitPayloadFromForm(kindOrKinds);
  const kinds = payload.kinds || ["face", "fullbody"];
  delete payload._checkpoint;
  const checkpoint = String(document.querySelector("#setupArtCheckpoint")?.value || "").trim();
  const gate = assessLocalArtReadiness(payload, { subject: "player" });
  if (!gate.can_generate) {
    setSetupArtStatus(formatArtReadinessMessage(gate), { bad: true });
    showImageMissingModal(gate);
    const card = document.querySelector("#characterPortraitCard");
    const faceFrame = card?.querySelector("[data-setup-face]");
    if (faceFrame) {
      const list = (gate.missing || [])
        .map((m) => `• ${escapeHtml(m.title || m.code || "Missing")}`)
        .join("<br/>");
      faceFrame.innerHTML = `<span class="visionBadge">blocked</span><div class="visionPlaceholder"><strong>Need more info</strong>${list || escapeHtml(gate.message || "")}</div>`;
    }
    syncPortraitControls();
    return null;
  }

  return enqueueGpuTask(async () => {
    const card = document.querySelector("#characterPortraitCard");
    const faceFrame = card?.querySelector("[data-setup-face]");
    const bodyFrame = card?.querySelector("[data-setup-fullbody]");
    const buttons = [...document.querySelectorAll("[data-art-kind]")];
    buttons.forEach((b) => {
      b.disabled = true;
    });
    setSetupArtStatus("Connecting to image backend (hook first, launch only if offline)…");
    if (kinds.includes("face") && faceFrame) {
      faceFrame.innerHTML = `<span class="visionBadge">face…</span><div class="visionPlaceholder"><strong>Generating face</strong>Local GPU — may take a minute.</div>`;
    }
    if (kinds.includes("fullbody") && bodyFrame) {
      bodyFrame.innerHTML = `<span class="visionBadge">body…</span><div class="visionPlaceholder"><strong>${kinds.includes("face") ? "Queued after face" : "Generating body"}</strong>${payload.use_face_reference ? " · face reference" : ""}</div>`;
    }
    try {
      if (!imageConfig) await loadImageConfig();
      // Persist checkpoint for the active character-art backend tab
      if (checkpoint) {
        const patch = { ...(imageConfig || {}) };
        if (setupArtBackendTab === "comfyui") {
          if (imageConfig?.comfy_checkpoint !== checkpoint) {
            patch.comfy_checkpoint = checkpoint;
            if (patch.provider === "off" || !patch.provider) patch.provider = "comfyui";
            await fetch("/api/image-config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(patch),
            })
              .then(async (r) => {
                if (r.ok) imageConfig = await r.json();
              })
              .catch(() => {});
          }
        } else if (imageConfig?.forge_checkpoint !== checkpoint) {
          patch.forge_checkpoint = checkpoint;
          await fetch("/api/image-config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
          })
            .then(async (r) => {
              if (r.ok) imageConfig = await r.json();
            })
            .catch(() => {});
        }
      }
      // Never send client-only keys; avoids accidental validation noise.
      const { _checkpoint: _ck, ...sendBody } = payload;
      const response = await fetch("/api/image/character-set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sendBody),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 422) {
          const msg = formatApiValidationError(result.detail, "Character art request invalid (422)");
          throw new Error(msg);
        }
        const detail =
          result.detail && typeof result.detail === "object"
            ? result.detail
            : { error: result.detail || result.error };
        showImageMissingModal(detail);
        throw new Error(typeof detail.error === "string" ? detail.error : "Character art failed");
      }
      applySetupArtResult(result, kinds);
      // New gens land in data/portraits — refresh setup library for pick/delete.
      refreshSetupImageLibrary({ silent: true }).catch(() => {});
      // Only fill empty engine fields from the run — never clobber longer user prompts.
      const faceEl = document.querySelector("#setupArtFacePrompt");
      const faceNeg = document.querySelector("#setupArtFaceNegative");
      const bodyEl = document.querySelector("#setupArtBodyPrompt");
      const bodyNeg = document.querySelector("#setupArtBodyNegative");
      const faceBuilt = result.face?.built_prompt || result.face?.prompt || "";
      const bodyBuilt = result.fullbody?.built_prompt || result.fullbody?.prompt || "";
      if (faceEl && faceBuilt && !String(faceEl.value || "").trim()) faceEl.value = faceBuilt;
      if (faceNeg && result.face?.negative_prompt && !String(faceNeg.value || "").trim()) {
        faceNeg.value = result.face.negative_prompt;
      }
      if (bodyEl && bodyBuilt && !String(bodyEl.value || "").trim()) bodyEl.value = bodyBuilt;
      if (bodyNeg && result.fullbody?.negative_prompt && !String(bodyNeg.value || "").trim()) {
        bodyNeg.value = result.fullbody.negative_prompt;
      }
      const secs = Math.round((result.elapsed_ms || 0) / 1000);
      const refNote =
        result.fullbody?.used_face_reference || result.face?.used_face_reference
          ? " · used other image as ref"
          : "";
      setSetupArtStatus(`Done (${secs}s) — ${kinds.join(" + ")}${refNote}.`);
      return result;
    } catch (error) {
      setSetupArtStatus(error.message || String(error), { bad: true });
      if (faceFrame && kinds.includes("face")) {
        faceFrame.innerHTML = `<span class="visionBadge">error</span><div class="visionPlaceholder"><strong>Art failed</strong>${escapeHtml(error.message || String(error))}</div>`;
      }
      throw error;
    } finally {
      buttons.forEach((b) => {
        b.disabled = false;
      });
      syncPortraitControls();
    }
  }, "Generating character art…");
}

function renderImageStudioCandidates() {
  const host = document.querySelector("#imageStudioCandidates");
  if (!host) return;
  if (!imageStudioCandidates.length) {
    host.innerHTML = `<p class="empty">No candidates yet. Generate face or body to fill the library.</p>`;
    return;
  }
  host.innerHTML = imageStudioCandidates
    .map(
      (c) => `
      <article class="imageStudioCandidate" data-cand-id="${escapeHtml(c.id)}">
        <img src="${c.data_url}" alt="${escapeHtml(c.kind)}" />
        <div class="candActions">
          <button type="button" class="secondaryButton" data-cand-use="face">Use face</button>
          <button type="button" class="secondaryButton" data-cand-use="fullbody">Use body</button>
        </div>
        <small class="empty">${escapeHtml(c.kind)}${c.used_face_reference ? " · ref" : ""} · seed ${escapeHtml(String(c.seed ?? "—"))}</small>
      </article>`,
    )
    .join("");
}

function useStudioCandidate(id, asKind) {
  const cand = imageStudioCandidates.find((c) => c.id === id);
  if (!cand?.data_url) return;
  const card = document.querySelector("#characterPortraitCard");
  if (asKind === "face") {
    lastSetupFaceDataUrl = cand.data_url;
    setArtFrameContent(card?.querySelector("[data-setup-face]"), {
      badge: "face",
      slot: "face",
      hasArt: true,
      html: `<img class="portraitImage" src="${cand.data_url}" alt="Character face" draggable="true" />`,
    });
    localStorage.setItem("morkyn-player-portrait", cand.data_url);
  } else {
    lastSetupBodyDataUrl = cand.data_url;
    setArtFrameContent(card?.querySelector("[data-setup-fullbody]"), {
      badge: "body · 3:4",
      slot: "fullbody",
      hasArt: true,
      html: `<img class="portraitImage portraitImageFull" src="${cand.data_url}" alt="Character full body" draggable="true" />`,
    });
    localStorage.setItem("morkyn-player-fullbody", cand.data_url);
  }
  setSetupArtStatus(`Applied candidate as ${asKind}.`);
  renderImageStudioCandidates();
}

function renderImageStudioHtml() {
  const primary = imageConfig?.primary_prompt || "";
  const primaryNeg = imageConfig?.primary_negative || imageConfig?.negative_prompt || "";
  const autoNpc = imageConfig?.auto_generate_npc_portraits ? "checked" : "";
  return `
    <div class="imageStudioPanel">
      <header>
        <h3>Image Studio</h3>
        <p class="empty">Layer A = game primary style. Layer C = session extra + LoRAs. Identity (B) is filled from setup / play state. Generate hooks Forge first, then starts it only if offline.</p>
      </header>
      <div class="imageStudioGrid">
        <label class="wide"><span>Primary positive (game-wide)</span>
          <textarea id="studioPrimaryPrompt" rows="3" maxlength="1200">${escapeHtml(primary)}</textarea>
        </label>
        <label class="wide"><span>Primary negative (game-wide)</span>
          <textarea id="studioPrimaryNegative" rows="3" maxlength="1200">${escapeHtml(primaryNeg)}</textarea>
        </label>
      </div>
      <label class="inlineCheck">
        <input type="checkbox" id="studioAutoNpc" ${autoNpc} />
        <span>Auto-generate portraits for new NPCs in play (not the player)</span>
      </label>
      <div class="visionActions artKindActions">
        <button type="button" class="secondaryButton" id="studioSavePrimary">Save primary prompts</button>
        <select id="studioArtGenKind" class="artGenSelect">
          <option value="both" selected>Face + body</option>
          <option value="face">Face only</option>
          <option value="fullbody">Body only</option>
        </select>
        <button type="button" class="secondaryButton" id="studioGenerateBtn" data-art-generate>Generate</button>
        <button type="button" class="secondaryButton" id="studioRefreshCatalog">Refresh catalog</button>
        <button type="button" class="secondaryButton" data-open-image-browser title="Infinite Image Browsing (if installed) or native portraits">Image Browser</button>
      </div>
      <p class="empty" id="studioStatus"></p>
      <h4>Candidates</h4>
      <div id="imageStudioCandidates" class="imageStudioCandidates"></div>
    </div>
  `;
}

function renderImageBrowserShellHtml() {
  return `
    <div class="imageBrowserPanel" id="imageBrowserPanel">
      <header class="imageBrowserHeader">
        <div>
          <h3>Image Browser</h3>
          <p class="empty imageBrowserStatus" id="imageBrowserStatus">Checking Infinite Image Browsing…</p>
        </div>
        <div class="artKindActions imageBrowserToolbar">
          <button type="button" class="secondaryButton chipBtn" data-iib-view="auto" title="Prefer IIB when online">Auto</button>
          <button type="button" class="secondaryButton chipBtn" data-iib-view="iib" title="Extension UI (localhost)">IIB</button>
          <button type="button" class="secondaryButton chipBtn" data-iib-view="native" title="Mørkyn data/portraits only">Portraits</button>
          <button type="button" class="secondaryButton chipBtn" data-iib-refresh title="Re-probe IIB + refresh list">Refresh</button>
          <button type="button" class="secondaryButton chipBtn" data-iib-open-tab title="Open IIB in a new browser tab">↗ Tab</button>
        </div>
      </header>
      <div class="imageBrowserBody" id="imageBrowserBody">
        <p class="empty">Loading…</p>
      </div>
    </div>
  `;
}

function renderNativePortraitGridHtml(items, filter = "all") {
  const list = Array.isArray(items) ? items : [];
  const q = String(filter || "all").toLowerCase();
  const filtered =
    q === "all" || !q
      ? list
      : list.filter((it) => String(it.kind || "") === q || String(it.name || "").toLowerCase().includes(q));
  if (!filtered.length) {
    return `<p class="empty">No portraits in <code>data/portraits</code> yet. Generate face/body art first, or install IIB under Forge to browse outputs. Drag library thumbs onto Face/Body frames after you generate.</p>`;
  }
  return `
    <div class="nativePortraitToolbar">
      <button type="button" class="chipBtn secondaryButton" data-portrait-filter="all">All</button>
      <button type="button" class="chipBtn secondaryButton" data-portrait-filter="face">Face</button>
      <button type="button" class="chipBtn secondaryButton" data-portrait-filter="fullbody">Body</button>
      <button type="button" class="chipBtn secondaryButton" data-portrait-filter="npc">NPC</button>
      <span class="empty nativePortraitHint">Drag a thumb onto Face/Body · or use Face / Body · Delete removes from disk</span>
    </div>
    <div class="nativePortraitGrid" role="list">
      ${filtered
        .map((it) => {
          const name = String(it.name || it.id || "");
          const url = String(it.url || "");
          const kind = String(it.kind || "other");
          return `
            <article class="nativePortraitCard" role="listitem" data-portrait-id="${escapeHtml(name)}" draggable="true" title="Drag onto Face or Full body">
              <button type="button" class="nativePortraitThumb" data-portrait-preview="${escapeHtml(name)}" title="${escapeHtml(name)} — drag to Face/Body">
                <img src="${escapeHtml(url)}" alt="" loading="lazy" draggable="true" data-portrait-drag-id="${escapeHtml(name)}" />
              </button>
              <div class="nativePortraitMeta">
                <span class="nativePortraitKind">${escapeHtml(kind)}</span>
                <span class="nativePortraitName" title="${escapeHtml(name)}">${escapeHtml(name.length > 28 ? `${name.slice(0, 26)}…` : name)}</span>
                <div class="nativePortraitActions">
                  <button type="button" class="chipBtn secondaryButton" data-portrait-use="face" data-portrait-id="${escapeHtml(name)}">Face</button>
                  <button type="button" class="chipBtn secondaryButton" data-portrait-use="fullbody" data-portrait-id="${escapeHtml(name)}">Body</button>
                  <button type="button" class="chipBtn secondaryButton dangerChip" data-portrait-delete="${escapeHtml(name)}" title="Delete this file from data/portraits">Delete</button>
                </div>
              </div>
            </article>`;
        })
        .join("")}
    </div>
  `;
}

let imageBrowserState = {
  iib: null,
  portraits: null,
  view: "auto", // auto | iib | native
};

async function fetchImageBrowserState({ launch = false } = {}) {
  const res = await fetch("/api/image-browser", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ launch_if_offline: !!launch }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Image browser status failed");
  imageBrowserState.iib = data.iib || null;
  imageBrowserState.portraits = data.portraits || null;
  return data;
}

function paintImageBrowserPanel() {
  const hosts = [
    ...document.querySelectorAll(
      "#imageBrowserBody, .imageBrowserBody, [data-popout-tab='imageBrowser'] .imageBrowserBody",
    ),
  ];
  const uniqueHosts = [...new Set(hosts)];
  if (!uniqueHosts.length) return;
  const iib = imageBrowserState.iib || {};
  const portraits = imageBrowserState.portraits || {};
  const view = imageBrowserState.view || "auto";
  // Float library: prefer native grid for pick/drag/delete; IIB when user picks IIB tab or Auto+online.
  const useIib =
    view === "iib" ||
    (view === "auto" && (iib.can_embed || (iib.online && iib.open_mode === "embed")));

  const statusEls = document.querySelectorAll("#imageBrowserStatus, .imageBrowserStatus");
  const count = Array.isArray(portraits.items) ? portraits.items.length : 0;
  statusEls.forEach((el) => {
    const base = iib.message || (useIib ? "IIB" : "Native portraits");
    el.textContent = useIib
      ? `${base} · drag header to move · Pin / collapse / resize corner`
      : `${base} · ${count} file${count === 1 ? "" : "s"} · drag · pin · resize`;
    el.classList.toggle("bad", !iib.online && view === "iib");
    el.classList.toggle("good", !!iib.online || count > 0);
  });

  const nativeNote = () => {
    if (!iib.installed_on_disk) {
      return `<p class="empty">IIB not installed — showing Mørkyn portraits. Install from <strong>LLM Settings → Images → Installs</strong>. Drag thumbs onto Face/Body, or Face / Body / Delete. Window: drag title bar, Pin, collapse —, resize corner.</p>`;
    }
    if (!iib.online) {
      return `<p class="empty">IIB offline — start Forge with --api, then Refresh. Native portraits: drag to Face/Body or Delete.</p>`;
    }
    if (iib.open_mode === "off") {
      return `<p class="empty">IIB open mode Off. Native portraits only.</p>`;
    }
    return `<p class="empty">Drag thumbs onto Face/Body · Face / Body buttons · Delete removes from disk. Drag the window title bar to move; Pin locks open; — collapses; corner resizes.</p>`;
  };

  uniqueHosts.forEach((body) => {
    if (useIib && iib.embed_url && iib.open_mode !== "off") {
      const src = String(iib.embed_url);
      // Combined: IIB iframe + always-visible native strip for pick/drag/delete
      body.innerHTML = `
        <div class="setupIibSplit imageBrowserSplit">
          <div class="iibEmbedWrap setupIibEmbed">
            <iframe
              class="iibEmbedFrame"
              title="Infinite Image Browsing (local extension)"
              src="${escapeHtml(src)}"
              referrerpolicy="no-referrer"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
            ></iframe>
            <p class="empty iibEmbedNote">
              IIB from your Forge · MIT ·
              <a href="${escapeHtml(src)}" target="_blank" rel="noopener noreferrer">Fullscreen</a>
              · use Portraits strip for drag/delete of Mørkyn gens
            </p>
          </div>
          <div class="nativePortraitHost setupNativeStrip">
            <h4 class="setupNativeStripTitle">Mørkyn portraits (pick · drag · delete)</h4>
            ${renderNativePortraitGridHtml(portraits.items || [], "all")}
          </div>
        </div>`;
    } else {
      body.innerHTML = `
        <div class="nativePortraitHost">
          ${nativeNote()}
          ${renderNativePortraitGridHtml(portraits.items || [], "all")}
        </div>`;
    }
  });
}

async function refreshSetupImageLibrary({ launch = false, silent = false } = {}) {
  const status = document.querySelector("#setupImageBrowserStatus");
  if (status && !silent) {
    status.textContent = "Refreshing library…";
    status.classList.remove("bad", "good");
  }
  try {
    await fetchImageBrowserState({ launch });
    paintImageBrowserPanel();
  } catch (err) {
    if (status) {
      status.textContent = err?.message || String(err);
      status.classList.add("bad");
    }
  }
}

async function deleteNativePortrait(name) {
  const id = String(name || "").trim();
  if (!id) return;
  if (!window.confirm(`Delete portrait file “${id}” from data/portraits? This cannot be undone.`)) {
    return;
  }
  const res = await fetch("/api/portraits/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: id }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.error || "Delete failed");
  }
  await refreshSetupImageLibrary({ silent: true });
  paintImageBrowserPanel();
  setSetupArtStatus?.(`Deleted ${id}.`);
}

async function openImageBrowser(mode = "float") {
  await probeImageBackendStatus({ silent: true });
  if (!requireImageBackendConnected("Image Library")) return;
  const key = "imageBrowser";
  if (mode === "window") {
    openTabWindow(key);
  } else {
    // Free-moving library: pinned open, resizable, collapsible chip when unpinned.
    const prev = floatWindowState[key] || {};
    const w = Math.max(480, Number(prev.width) || 920);
    const h = Math.max(360, Number(prev.height) || 680);
    const left = prev.left != null ? prev.left : Math.max(24, Math.round(window.innerWidth * 0.08));
    const top = prev.top != null ? prev.top : Math.max(48, Math.round(window.innerHeight * 0.1));
    floatWindowState[key] = {
      ...prev,
      open: true,
      pinned: true,
      collapsed: false,
      width: w,
      height: h,
      left,
      top,
    };
    openTabFloat(key, { pinned: true, width: w, height: h, left, top });
    const panel = floatPanels[key];
    if (panel) {
      panel.classList.add("isPinned");
      panel.classList.remove("isCollapsed");
      panel.style.setProperty("--float-w", `${w}px`);
      panel.style.setProperty("--float-h", `${h}px`);
      panel.style.width = `${w}px`;
      panel.style.height = `${h}px`;
      panel.style.left = `${left}px`;
      panel.style.top = `${top}px`;
      applyFloatPanelChrome(panel, key);
      raiseFloatPanel(panel);
      persistFloatPanel(key, panel);
    }
  }
  const fill = async () => {
    const panel = floatPanels[key];
    const body = panel?.querySelector("[data-float-body]");
    if (body) {
      body.innerHTML = renderImageBrowserShellHtml();
      decorateFunctionHelp(body);
    }
    const win = popoutWindows[key];
    if (win && !win.closed) {
      try {
        win.postMessage(
          { type: "morkyn-popout", tab: key, html: renderImageBrowserShellHtml(), theme: getUiTheme() },
          window.location.origin,
        );
      } catch (_) {
        /* ignore */
      }
    }
    try {
      await fetchImageBrowserState({ launch: false });
      paintImageBrowserPanel();
      if (imageBrowserState.iib?.open_mode === "tab" && imageBrowserState.iib?.online) {
        imageBrowserState.view = "native";
        paintImageBrowserPanel();
      }
    } catch (err) {
      const status = document.querySelector("#imageBrowserStatus, .imageBrowserStatus");
      if (status) {
        status.textContent = err?.message || String(err);
        status.classList.add("bad");
      }
      const host = document.querySelector("#imageBrowserBody");
      if (host) {
        host.innerHTML = `<p class="bad">${escapeHtml(err?.message || String(err))}</p>`;
      }
    }
  };
  setTimeout(() => {
    fill().catch(() => {});
  }, 0);
}

async function openImageStudio(mode = "float") {
  await probeImageBackendStatus({ silent: true });
  if (!requireImageBackendConnected("Image Studio")) return;
  // Reuse float panel infrastructure with a synthetic tab key.
  const key = "imageStudio";
  if (mode === "window") {
    openTabWindow(key);
  } else {
    openTabFloat(key);
    const panel = floatPanels[key];
    if (panel) {
      panel.classList.add("isPinned");
      panel.classList.remove("isCollapsed");
      applyFloatPanelChrome(panel, key);
      // Wider default for studio work.
      panel.style.width = panel.style.width || "720px";
      panel.style.height = panel.style.height || "640px";
    }
  }
  setTimeout(() => {
    const panel = floatPanels[key];
    const body = panel?.querySelector("[data-float-body]");
    if (body) {
      body.innerHTML = renderImageStudioHtml();
      renderImageStudioCandidates();
      decorateFunctionHelp(body);
    }
    const win = popoutWindows[key];
    if (win && !win.closed) {
      try {
        win.postMessage(
          { type: "morkyn-popout", tab: key, html: renderImageStudioHtml(), theme: getUiTheme() },
          window.location.origin,
        );
      } catch (_) {
        /* ignore */
      }
    }
    refreshSetupArtCatalog();
    renderImageStudioCandidates();
  }, 40);
}

async function searchImageBackendRoot(kind, form) {
  const status =
    form?.parentElement?.querySelector("[data-image-status]") ||
    document.querySelector("[data-image-status]");
  if (status) status.innerHTML = `<p class="empty">Searching common folders for ${escapeHtml(kind)}… (consented scan)</p>`;
  const response = await fetch("/api/image-path-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, max_results: 12, max_seconds: 12 }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || payload.error || "Search failed");
  const candidates = payload.candidates || [];
  if (!candidates.length) {
    if (status) status.innerHTML = `<p class="bad">${escapeHtml(payload.message || "No installs found. Enter the path manually.")}</p>`;
    return payload;
  }
  const lines = candidates.map((c, i) => `${i + 1}. ${c.path}`).join("\n");
  const pick = window.prompt(
    `Found ${candidates.length} candidate(s) for ${kind}.\nEnter a number to use that path, or Cancel.\n\n${lines}`,
    "1",
  );
  if (pick == null) {
    if (status) status.innerHTML = `<p class="empty">Search cancelled — enter path manually if needed.</p>`;
    return payload;
  }
  const index = Math.max(1, Math.min(candidates.length, parseInt(pick, 10) || 1)) - 1;
  const chosen = candidates[index];
  const path = String(chosen?.path || "").trim();
  if (!path) {
    if (status) status.innerHTML = `<p class="bad">Invalid selection.</p>`;
    return payload;
  }
  // Keep in memory so re-renders / later Save don't wipe the choice.
  if (kind === "forge") pendingImageRoots.forge = path;
  else pendingImageRoots.comfyui = path;
  const input = form?.querySelector(
    kind === "forge" ? 'input[name="forge_root"]' : 'input[name="comfy_root"]',
  );
  if (input) input.value = path;
  // Persist immediately (no form re-render) so Launch works even if the field looks empty later.
  try {
    const patch = {
      ...(imageConfig || {}),
      provider: form?.querySelector('[name="provider"]')?.value || imageConfig?.provider || "off",
      forge_root: pendingImageRoots.forge || imageConfig?.forge_root || "",
      comfy_root: pendingImageRoots.comfyui || imageConfig?.comfy_root || "",
    };
    if (form) Object.assign(patch, imagePayloadFromForm(form));
    if (kind === "forge") patch.forge_root = path;
    else patch.comfy_root = path;
    const saveRes = await fetch("/api/image-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (saveRes.ok) {
      imageConfig = await saveRes.json();
    }
  } catch (_) {
    /* still keep pending path */
  }
  if (status) {
    status.innerHTML = `<p class="good">Selected and saved: <code>${escapeHtml(path)}</code></p>`;
  }
  return payload;
}

async function checkImageReadiness(container) {
  const status = container.querySelector("[data-image-status]");
  const form = container.querySelector("#imageForm");
  if (form) await saveImageConfig(form, { rerender: false });
  if (status) status.innerHTML = `<p class="empty">Checking readiness…</p>`;
  const response = await fetch("/api/image-readiness", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ launch_if_offline: false }),
  });
  const payload = await response.json().catch(() => ({}));
  const missing = payload.missing || [];
  if (status) {
    if (payload.api_ok) {
      status.innerHTML = `<p class="good">${escapeHtml(payload.api_message || "API ready")}</p>`;
    } else {
      const list = missing.map((m) => `<li>${escapeHtml(m.title || m.code || "")}: ${escapeHtml(m.detail || "")}</li>`).join("");
      status.innerHTML = `<p class="bad">${escapeHtml(payload.api_message || "Not ready")}</p><ul class="empty">${list}</ul>`;
    }
  }
  forgeImageStatus = {
    ok: !!payload.api_ok,
    provider: payload.provider || imageConfig?.provider || "off",
    message: payload.api_message || payload.message || "",
    raw: payload,
  };
  syncForgeImageGateUi();
  return payload;
}

async function launchImageBackendFromUi(container, event) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  // Stay on current screen (setup or game) — do not navigate to main menu.
  const status = container?.querySelector?.("[data-image-status]") || document.querySelector("[data-image-status]");
  const form = container?.querySelector?.("#imageForm") || document.querySelector("#imageForm");
  if (form) await saveImageConfig(form, { rerender: false });
  const provider = form?.querySelector('[name="provider"]')?.value || imageConfig?.provider || "off";
  const rootHint =
    provider === "comfyui"
      ? pendingImageRoots.comfyui || imageConfig?.comfy_root || "(empty)"
      : pendingImageRoots.forge || imageConfig?.forge_root || "(empty)";

  // 1) Probe first — if already up, do not open a new terminal.
  if (status) {
    status.innerHTML = `<p class="empty">Checking if ${escapeHtml(provider)} API is already running…</p>`;
  }
  try {
    const probeRes = await fetch("/api/image-status", { method: "POST" });
    const probe = await probeRes.json().catch(() => ({}));
    if (probe.ok && provider !== "off") {
      if (status) {
        status.innerHTML = `<p class="good">Backend already running — ${escapeHtml(probe.message || "API OK")}. Not opening another terminal. Studio & Image Library unlock on Character art.</p>`;
      }
      forgeImageStatus = {
        ok: true,
        provider: probe.provider || provider,
        message: probe.message || "API OK",
        raw: probe,
      };
      syncForgeImageGateUi();
      loadImageCatalog(provider).catch(() => {});
      return { ok: true, already_running: true, message: probe.message, probe };
    }
  } catch (_) {
    /* fall through to launch */
  }

  if (status) {
    status.innerHTML = `<p class="empty">API offline — starting headless ${escapeHtml(provider)}… root=${escapeHtml(rootHint)}</p>`;
  }
  const response = await fetch("/api/image-launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, force: false }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.error || "Launch failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (status) {
    const kind = payload.already_running
      ? "good"
      : payload.pending
        ? "empty"
        : "good";
    status.innerHTML = `<p class="${kind}">${escapeHtml(
      payload.message || "Backend start requested",
    )}</p>`;
  }
  // Refresh checkpoint list + unlock Studio/Library after boot window.
  window.setTimeout(() => {
    loadImageCatalog(provider).catch(() => {});
    probeImageBackendStatus({ silent: true }).catch(() => {});
  }, 4000);
  return payload;
}

async function selectModelFile(form) {
  const response = await fetch("/api/select-model-file", { method: "POST" });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  if (payload.path) form.querySelector('[name="gguf_model_path"]').value = payload.path;
}

/**
 * Native folder picker for Forge/Comfy roots (or any custom directory).
 * Writes all matching inputs in the form, updates pendingImageRoots, optionally soft-saves.
 */
async function browseBackendRoot(kind, form, { save = true } = {}) {
  const kindKey = kind === "comfy" || kind === "comfyui" ? "comfyui" : "forge";
  const fieldName = kindKey === "forge" ? "forge_root" : "comfy_root";
  const current =
    form?.querySelector?.(`input[name="${fieldName}"]`)?.value ||
    (kindKey === "forge" ? pendingImageRoots.forge : pendingImageRoots.comfyui) ||
    imageConfig?.[fieldName] ||
    "";
  const status =
    form?.parentElement?.querySelector("[data-image-status]") ||
    document.querySelector("[data-image-status]");
  if (status) {
    status.innerHTML = `<p class="empty">Opening folder picker for ${escapeHtml(kindKey)}…</p>`;
  }
  const response = await fetch("/api/select-folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: kindKey,
      initial_dir: String(current || "").trim(),
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || "Folder picker failed");
  }
  const path = String(payload.path || "").trim();
  if (!path) {
    if (status) status.innerHTML = `<p class="empty">No folder selected.</p>`;
    return payload;
  }
  if (kindKey === "forge") pendingImageRoots.forge = path;
  else pendingImageRoots.comfyui = path;
  // Update every matching input (Forge tab + Installs tab can both have one)
  form?.querySelectorAll?.(`input[name="${fieldName}"]`).forEach((input) => {
    input.value = path;
  });
  document.querySelectorAll(`#imageForm input[name="${fieldName}"]`).forEach((input) => {
    input.value = path;
  });
  if (save) {
    try {
      const patch = {
        ...(imageConfig || {}),
        provider: form?.querySelector?.('[name="provider"]')?.value || imageConfig?.provider || "off",
        forge_root: pendingImageRoots.forge || imageConfig?.forge_root || "",
        comfy_root: pendingImageRoots.comfyui || imageConfig?.comfy_root || "",
      };
      if (kindKey === "forge") patch.forge_root = path;
      else patch.comfy_root = path;
      const saveRes = await fetch("/api/image-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (saveRes.ok) {
        imageConfig = await saveRes.json();
      }
    } catch (_) {
      /* keep local path even if save fails */
    }
  }
  const warn =
    payload.looks_valid === false
      ? ` <em class="muted">(${escapeHtml(payload.message || "path may not look like a typical install")})</em>`
      : "";
  if (status) {
    status.innerHTML = `<p class="good">Folder set: <code>${escapeHtml(path)}</code>${warn}</p>`;
  }
  // Refresh install checklist if present
  refreshImageInstallablesPanel(form?.closest?.(".modalPanel") || modelModalContent).catch(() => {});
  return payload;
}

async function testModelConnection(container) {
  const status = container.querySelector("[data-model-status]");
  const form = container.querySelector("#modelForm") || container.closest(".modalPanel")?.querySelector("#modelForm") || document.querySelector("#modelForm");
  if (status) status.innerHTML = `<p class="empty">Saving settings and checking LLM server...</p>`;
  if (form) {
    const saveResponse = await fetch("/api/model-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(modelPayloadFromForm(form)),
    });
    if (!saveResponse.ok) throw new Error(await saveResponse.text());
    modelConfig = await saveResponse.json();
  }
  if (status) status.innerHTML = `<p class="empty">Checking LLM server. If llama.cpp is not running, this may start it from the selected GGUF model...</p>`;
  const response = await fetch("/api/model-status");
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  if (!status) return;
  if (payload.ok) {
    const models = (payload.models || []).length ? ` Models: ${(payload.models || []).map(escapeHtml).join(", ")}` : "";
    const start = payload.managed_start?.started ? " Started managed llama.cpp server." : "";
    status.innerHTML = `<p class="good">Connection OK. ${escapeHtml(payload.url || "")}${escapeHtml(start)}${models}</p>`;
  } else {
    const logs = payload.managed_start?.logs;
    const logText = logs?.stderr_tail || logs?.stdout_tail || "";
    status.innerHTML = `<p class="bad">Connection failed at ${escapeHtml(payload.url || "")}: ${escapeHtml(payload.error || "unknown error")}</p>${logText ? `<pre class="modelLogTail">${escapeHtml(logText)}</pre>` : ""}`;
  }
}

function showEntity(code) {
  const found = getEntityMap().get(String(code).toUpperCase());
  if (!found) return;
  selectedEntity = found;
  const { type, entity } = found;
  entityTitle.textContent = entityLabel(entity);
  entityMeta.textContent = `${type.toUpperCase()} ${entity.code} · insert as ${refToken(type, entity.code)}`;

  let body = "";
  if (type === "npc") {
    const talks = (state.conversations || []).filter((talk) => talk.npc_code === entity.code);
    const statText = profileLine(entity.stat_profile);
    const skillText = profileLine(entity.skill_profile);
    const combatText = npcCombatLine(entity);
    body = `
      <p>${escapeHtml(entity.summary || "No summary.")}</p>
      <p><strong>Race:</strong> ${escapeHtml(entity.race || "human")} · <strong>Role:</strong> ${escapeHtml(entity.role)} · <strong>Rank:</strong> ${escapeHtml(entity.rank || "F")} · <strong>Attitude:</strong> ${escapeHtml(entity.attitude)} · <strong>Trust:</strong> ${escapeHtml(entity.trust ?? 0)}</p>
      ${combatText ? `<p><strong>Combat:</strong> ${escapeHtml(combatText)}</p>` : ""}
      <p><strong>Stats:</strong> ${escapeHtml(statText || "Not observed yet.")}</p>
      <p><strong>Skills:</strong> ${escapeHtml(skillText || "No notable skills indexed.")}</p>
      <p><strong>Personality:</strong> ${escapeHtml(entity.personality || "Unknown")}</p>
      <p><strong>Likes:</strong> ${escapeHtml(entity.likes || "Unknown")}</p>
      <p><strong>Principles:</strong> ${escapeHtml(entity.principles || "Unknown")}</p>
      <p><strong>Dislikes:</strong> ${escapeHtml(entity.dislikes || "Unknown")}</p>
      <p><strong>Talk:</strong> ${talks.length ? escapeHtml(talks.map((talk) => `T${talk.turn}: ${talk.summary}`).join(" | ")) : "No conversations indexed."}</p>
    `;
  } else if (type === "event") {
    body = `<p>${escapeHtml(entity.summary || "No summary.")}</p><p><strong>Status:</strong> ${escapeHtml(entity.status)} · <strong>Location:</strong> ${escapeHtml(entity.location_code || "?")} · <strong>NPC:</strong> ${escapeHtml(entity.npc_code || "?")}</p>`;
  } else if (type === "location") {
    body = `<p>${escapeHtml(entity.summary || "No summary.")}</p><p><strong>Visits:</strong> ${escapeHtml(entity.visit_count)} · <strong>NPCs:</strong> ${escapeHtml(entity.npcs?.length || 0)}</p>`;
  } else {
    body = `<p>${escapeHtml(entity.description || "No description.")}</p><p><strong>Quantity:</strong> ${escapeHtml(entity.quantity || 0)}</p>`;
  }
  entityBody.innerHTML = body;
  aliasInput.value = "";
  entityMenu.classList.remove("hidden");
}

function updateConditionalSetup() {
  const system = setupForm.querySelector('input[name="game_system"]:checked')?.value === "true";
  systemOptions.classList.toggle("open", system);
  formerLifeIdentity?.classList.toggle("open", formerLifeSelected());
  updateCustomControls();
  updateAbilityOriginControls();
}

async function loadState() {
  const response = await fetch("/api/state");
  if (!response.ok) throw new Error("Could not load state.");
  renderShell(await response.json());
}

function buildTurnDebugBundle(payload) {
  const turn = payload?.turn || {};
  const existing = payload?.debug && typeof payload.debug === "object" ? { ...payload.debug } : {};
  const selfCheck = existing.self_check || turn.self_check || {};
  const passed = selfCheck.passed === true || selfCheck.ok === true;
  const path = String(existing.trace_path || payload?.debug_trace_path || "").trim();
  const name = String(existing.trace_name || (path ? path.split(/[/\\]/).pop() : "")).trim();
  return {
    turn: existing.turn ?? null,
    input_kind: existing.input_kind || payload?.input_kind || "",
    used_fallback: Boolean(existing.used_fallback ?? payload?.used_fallback),
    fallback_reason: existing.fallback_reason || payload?.fallback_reason || "",
    self_check: selfCheck,
    self_check_passed: passed,
    model_usage: Array.isArray(existing.model_usage) ? existing.model_usage : [],
    pipeline_phases: Array.isArray(existing.pipeline_phases) ? existing.pipeline_phases : [],
    narration_pipeline: existing.narration_pipeline || turn._narration_pipeline || null,
    narration_chars: existing.narration_chars ?? String(turnNarrationText(turn) || "").length,
    trace_path: path,
    trace_name: name,
  };
}

function turnDebugSummaryText(bundle) {
  const check = bundle.self_check || {};
  const status = bundle.self_check_passed ? "passed" : "needs review";
  const usage = (bundle.model_usage || [])
    .slice(-8)
    .map((row) => {
      const phase = row?.phase || "phase";
      const chars = row?.chars != null ? `${row.chars}c` : "";
      const err = row?.error ? ` err=${clipText(String(row.error), 80)}` : "";
      return `${phase}${chars ? ` ${chars}` : ""}${err}`;
    })
    .filter(Boolean);
  const phases = (bundle.pipeline_phases || [])
    .slice(-6)
    .map((row) => [row?.phase, row?.event].filter(Boolean).join("/"))
    .filter(Boolean);
  return [
    `Check: ${status}${check.consistency_check ? ` · ${check.consistency_check}` : ""}`,
    bundle.input_kind ? `Kind: ${bundle.input_kind}` : "",
    bundle.narration_chars != null ? `Narration: ${bundle.narration_chars} chars` : "",
    bundle.used_fallback ? `Fallback: ${clipText(bundle.fallback_reason || "yes", 160)}` : "Fallback: no",
    usage.length ? `Usage: ${usage.join(" · ")}` : "",
    phases.length ? `Phases: ${phases.join(" → ")}` : "",
    bundle.trace_name ? `Trace file: ${bundle.trace_name}` : "",
    bundle.trace_path ? `Path: ${bundle.trace_path}` : "",
  ].filter(Boolean).join("\n");
}

function turnDebugPanelHtml(payload) {
  const bundle = buildTurnDebugBundle(payload);
  const jsonText = JSON.stringify(bundle, null, 2);
  const summary = turnDebugSummaryText(bundle);
  const statusClass = bundle.self_check_passed ? "passed" : "failed";
  const statusLabel = bundle.self_check_passed ? "ok" : "review";
  const id = `turn-debug-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e4)}`;
  return `
    <section class="turnDebugPanel" data-turn-debug>
      <button type="button" class="turnDebugToggle" data-debug-toggle aria-expanded="false" aria-controls="${id}">
        <span class="turnDebugChevron" aria-hidden="true">▸</span>
        <strong>Debug</strong>
        <span class="turnDebugStatus ${statusClass}">${escapeHtml(statusLabel)}</span>
        ${bundle.trace_name ? `<span class="turnDebugFile">${escapeHtml(bundle.trace_name)}</span>` : ""}
      </button>
      <div id="${id}" class="turnDebugBody hidden" hidden>
        <div class="turnDebugActions">
          <button type="button" class="secondaryButton compactButton" data-debug-copy="summary">Copy summary</button>
          <button type="button" class="secondaryButton compactButton" data-debug-copy="json">Copy JSON</button>
          ${bundle.trace_path ? `<button type="button" class="secondaryButton compactButton" data-debug-copy="path">Copy path</button>` : ""}
          ${bundle.trace_name ? `<button type="button" class="secondaryButton compactButton" data-debug-view-file>View file</button>` : ""}
        </div>
        <pre class="turnDebugSummary" data-debug-summary>${escapeHtml(summary)}</pre>
        <pre class="turnDebugJson hidden" data-debug-json hidden>${escapeHtml(jsonText)}</pre>
        <pre class="turnDebugFileView hidden" data-debug-file-view hidden></pre>
        <p class="turnDebugHint">Trace files live under <code>data/model_traces/</code> on the server machine. Expand only when you need them.</p>
      </div>
    </section>
  `;
}

async function copyTextToClipboard(text) {
  const value = String(text || "");
  if (!value) return false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* fall through */
  }
  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

function bindTurnDebugPanel(root = latestOutput) {
  if (!root) return;
  root.querySelectorAll("[data-turn-debug]").forEach((panel) => {
    if (panel.dataset.bound === "1") return;
    panel.dataset.bound = "1";
    const toggle = panel.querySelector("[data-debug-toggle]");
    const body = panel.querySelector(".turnDebugBody");
    const summaryEl = panel.querySelector("[data-debug-summary]");
    const jsonEl = panel.querySelector("[data-debug-json]");
    const fileView = panel.querySelector("[data-debug-file-view]");
    const chevron = panel.querySelector(".turnDebugChevron");

    toggle?.addEventListener("click", () => {
      const open = body && !body.classList.contains("hidden");
      if (!body) return;
      if (open) {
        body.classList.add("hidden");
        body.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        if (chevron) chevron.textContent = "▸";
      } else {
        body.classList.remove("hidden");
        body.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
        if (chevron) chevron.textContent = "▾";
      }
    });

    panel.querySelectorAll("[data-debug-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mode = btn.getAttribute("data-debug-copy");
        let text = "";
        if (mode === "summary") text = summaryEl?.textContent || "";
        else if (mode === "json") text = jsonEl?.textContent || "";
        else if (mode === "path") {
          text = "";
          try {
            const parsed = JSON.parse(jsonEl?.textContent || "{}");
            text = parsed.trace_path || "";
          } catch {
            /* ignore */
          }
          if (!text) {
            const match = (summaryEl?.textContent || "").match(/^Path:\s*(.+)$/m);
            text = match ? match[1].trim() : "";
          }
        }
        const ok = await copyTextToClipboard(text);
        const prev = btn.textContent;
        btn.textContent = ok ? "Copied" : "Copy failed";
        window.setTimeout(() => {
          btn.textContent = prev;
        }, 1200);
      });
    });

    panel.querySelector("[data-debug-view-file]")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      let name = "";
      try {
        const parsed = JSON.parse(jsonEl?.textContent || "{}");
        name = parsed.trace_name || "";
      } catch {
        name = "";
      }
      if (!name && summaryEl?.textContent) {
        const m = summaryEl.textContent.match(/^Trace file:\s*(.+)$/m);
        name = m ? m[1].trim() : "";
      }
      if (!name || !fileView) return;
      const prev = btn.textContent;
      btn.textContent = "Loading…";
      btn.disabled = true;
      try {
        const response = await fetch(`/api/debug-trace?name=${encodeURIComponent(name)}`, { cache: "no-store" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
        const pretty = data.json
          ? JSON.stringify(data.json, null, 2)
          : String(data.text || "");
        fileView.textContent = pretty || "(empty file)";
        fileView.classList.remove("hidden");
        fileView.hidden = false;
        btn.textContent = "File loaded";
      } catch (error) {
        fileView.textContent = `Could not load trace: ${error.message || error}`;
        fileView.classList.remove("hidden");
        fileView.hidden = false;
        btn.textContent = "Load failed";
      } finally {
        window.setTimeout(() => {
          btn.textContent = prev;
          btn.disabled = false;
        }, 1400);
      }
    });
  });
}

function skillChecksHtml(payload) {
  const checks = Array.isArray(payload?.skill_checks)
    ? payload.skill_checks
    : Array.isArray(payload?.turn?.skill_checks)
      ? payload.turn.skill_checks
      : [];
  const visible = checks.filter((c) => c && c.enabled !== false && (c.natural != null || c.display_block || c.display));
  if (!visible.length) return "";
  return visible
    .map((check) => {
      const outcome = String(check.outcome || check.degree || "check").replace(/_/g, " ");
      const degree = String(check.degree || "").replace(/_/g, " ");
      const skillName = check.skill?.name || check.skill_code || "Check";
      const lines = Array.isArray(check.lines) && check.lines.length
        ? check.lines
        : String(check.display_block || check.display || "").split("\n").filter(Boolean);
      const opp = check.opposition
        ? `<div class="rollOpp">vs <strong>${escapeHtml(check.opposition.name || "opposition")}</strong> power ${escapeHtml(check.opposition.power_total ?? "?")}${check.opposition.rank ? ` · rank ${escapeHtml(check.opposition.rank)}` : ""}</div>`
        : "";
      const injury = check.injury
        ? `<div class="rollInjury"><strong>Injury:</strong> ${escapeHtml(check.injury.summary || check.injury.limb || "hurt")}</div>`
        : "";
      return `
        <section class="rollBanner outcome-${escapeHtml(String(check.outcome || "failure"))}" aria-label="Skill check result">
          <header>
            <strong>${escapeHtml(skillName)}</strong>
            <span class="rollOutcome">${escapeHtml(outcome)}${degree && degree !== outcome ? ` · ${escapeHtml(degree)}` : ""}</span>
          </header>
          <div class="rollMath">
            <div>You rolled <b>${escapeHtml(check.natural)}</b> with your base of <b>${escapeHtml(check.base ?? check.attribute_score ?? "?")}</b> and a modifier of <b>${escapeHtml((check.modifier >= 0 ? "+" : "") + (check.modifier ?? 0))}</b>.</div>
            <div>Total <b>${escapeHtml(check.total)}</b> · Base success (DC): <b>${escapeHtml(check.base_success ?? check.dc ?? "?")}</b></div>
          </div>
          ${opp}
          <p class="rollFlavor">${escapeHtml(check.flavor || lines[lines.length - 1] || "")}</p>
          ${injury}
          <pre class="rollLines">${escapeHtml(lines.join("\n"))}</pre>
        </section>
      `;
    })
    .join("");
}

function appendTurnMeta(payload) {
  const rewardsHtml = turnRewardsHtml(payload);
  if (rewardsHtml) latestOutput.innerHTML += rewardsHtml;
  const rollsHtml = skillChecksHtml(payload);
  if (rollsHtml) latestOutput.innerHTML += rollsHtml;
  const planHtml = scenePlanHtml(payload.turn?.scene_plan);
  if (planHtml) latestOutput.innerHTML += planHtml;
  if (payload.used_fallback) {
    const reason = payload.fallback_reason || payload.turn?.llm_error || "No detailed error returned.";
    const notice = payload.fallback_notice || fallbackNoticeText(reason);
    latestOutput.innerHTML += `
      <section class="fallbackNotice">
        <strong>Fallback narration generated.</strong>
        <p>${escapeHtml(notice)}</p>
        <small>Model issue: ${escapeHtml(clipText(reason, 420))}</small>
      </section>
    `;
  }
  // Collapsed by default — expand to copy summary/JSON or view the trace file.
  latestOutput.innerHTML += turnDebugPanelHtml(payload);
  bindTurnDebugPanel(latestOutput);
}

function turnRewardsHtml(payload) {
  const rewards = payload.rewards || {};
  const turn = payload.turn || {};
  const playerPatch = turn.player || {};
  const xpGain = Math.max(0, Number(rewards.xp_gain ?? playerPatch.xp_delta ?? 0) || 0);
  const rawItems = Array.isArray(rewards.items_gained)
    ? rewards.items_gained
    : (Array.isArray(turn.inventory_changes) ? turn.inventory_changes : []).filter((item) => Number(item?.quantity_delta || 0) > 0);
  const items = rawItems
    .map((item) => ({
      name: String(item?.name || "").trim(),
      quantity: Math.max(0, Number(item?.quantity ?? item?.quantity_delta ?? 0) || 0),
      rarity: String(item?.rarity || "").trim(),
      itemType: String(item?.item_type || item?.type || "").trim(),
      description: String(item?.description || "").trim(),
    }))
    .filter((item) => item.name && item.quantity > 0);
  if (!xpGain && !items.length) return "";
  const itemRows = items.map((item) => {
    const details = [item.rarity, item.itemType].filter(Boolean).join(" ");
    const meta = [details, item.description].filter(Boolean).join(" - ");
    return `
      <li>
        <span class="rewardAmount">+${escapeHtml(item.quantity)}</span>
        <span class="rewardName">${escapeHtml(item.name)}</span>
        ${meta ? `<span class="rewardMeta">${escapeHtml(meta)}</span>` : ""}
      </li>
    `;
  }).join("");
  return `
    <section class="rewardBanner" aria-label="Turn rewards gained">
      <strong>Rewards Gained</strong>
      <div class="rewardSummary">
        ${xpGain ? `<div class="rewardPill"><span>XP</span><b>+${escapeHtml(Math.round(xpGain))}</b></div>` : ""}
        ${items.length ? `<div class="rewardPill"><span>Items</span><b>+${escapeHtml(items.reduce((total, item) => total + item.quantity, 0))}</b></div>` : ""}
      </div>
      ${itemRows ? `<ul class="rewardItems">${itemRows}</ul>` : ""}
    </section>
  `;
}

function displayTurnPayload(payload, options = {}) {
  clearTurnWaitTimer();
  if (!payload?.state || !payload?.turn) return false;
  clearSuggestions();
  renderShell(payload.state);
  // After any turn resolves, narration is the main stage (map is secondary).
  setSceneFocus(true, { scroll: true, focusInput: false, smooth: false });
  const narrationText = turnNarrationText(payload.turn) || "The world hesitates.";
  if (options.startSplash) {
    scenePlanLines(payload.turn.scene_plan).forEach(addStartSplashLine);
    addStartSplashLine("Opening scene received. Revealing prose.");
  }
  if (options.animateNarration) {
    latestOutput.innerHTML = `<article class="turnNarration streaming" data-turn-narration></article>`;
    const narrationEl = latestOutput.querySelector("[data-turn-narration]");
    const splashTargets = options.startSplash && startSplashDraft ? [startSplashDraft] : [];
    if (startSplashDraft && options.startSplash) startSplashDraft.classList.add("startSplashCursor");
    streamTextToTargets(narrationText, [narrationEl, ...splashTargets], () => {
      if (narrationEl) {
        narrationEl.classList.remove("streaming");
        narrationEl.innerHTML = paragraphs(narrationText);
      }
      appendTurnMeta(payload);
      if (options.startSplash) {
        addStartSplashLine("Opening scene is ready.");
        window.setTimeout(hideStartSplash, 1200);
      }
    }, { durationMs: options.startSplash ? 9000 : 4200 });
  } else {
    latestOutput.innerHTML = turnNarrationHtml(payload.turn);
    appendTurnMeta(payload);
  }
  return true;
}

async function requestTurn(text, options = {}) {
  const cleanText = String(text || "").trim();
  const isContinue = !cleanText;
  const displayText = options.displayText || (isContinue ? "Continue" : cleanText);
  latestInput.innerHTML = paragraphs(displayText);
  showTurnWaitPanel(isContinue ? "Continuing scene" : "Writing response", isContinue ? "continue" : "turn");
  clearSuggestions();
  if (turnInput) {
    turnInput.value = "";
    updateComposerState();
  }

  let payload = null;
  try {
    const response = await fetch(isContinue ? "/api/continue" : "/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: isContinue ? undefined : JSON.stringify({ text: cleanText }),
    });
    if (!response.ok) throw new Error(await response.text());
    payload = await response.json();
  } finally {
    clearTurnWaitTimer();
  }
  if (!displayTurnPayload(payload, { animateNarration: true })) throw new Error("Turn response did not include narration.");
}

async function requestSuggestions(instruction = "") {
  if (!suggestionsEl || !suggestionPanel) return;
  suggestionPanel.classList.remove("hidden");
  suggestionsEl.innerHTML = `<p class="suggestionStatus">Thinking...</p>`;
  const cleanInstruction = String(instruction || "").trim();
  const response = await fetch("/api/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction: cleanInstruction }),
  });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  renderSuggestions(Array.isArray(payload) ? payload : payload.suggestions || []);
}

async function startGame(event) {
  event.preventDefault();
  if (aiBusy) return;
  const startLabel = "Starting playthrough...";
  showStartSplash();
  await enqueueAiTask(withSetupRandomizationLock(async () => {
    latestOutput.innerHTML = paragraphs("Starting playthrough and writing the opening scene...");
    const formData = new FormData(setupForm);
    const skillCustom = readCustomText("skill_style");
    const xpGain = readGainSetting("xp_growth_speed");
    const skillGain = readGainSetting("skill_growth_speed");
    const proficiencyGain = readGainSetting("proficiency_growth_speed");
    const customSkillsField = setupForm.elements.custom_skills;
    const customSkillsText = commaSeparatedPhrases(formData.get("custom_skills"));
    if (customSkillsField) customSkillsField.value = customSkillsText;
    const customSkills = commaSeparatedPhrases([customSkillsText, skillCustom ? `Skill learning rule: ${skillCustom}` : ""]);
    const specialAbilityOrigin = abilityOrigin();
    const specialAbilities = specialAbilityOrigin === "none" ? [] : collectAbilities();
    const includeFormerLife = formerLifeSelected(formData);
    const setupPayload = {
      player_name: textField(formData, "player_name", "Wanderer", 80),
      player_public_name: textField(formData, "player_public_name", "", 100),
      player_title: textField(formData, "player_title", "", 100),
      player_age: textField(formData, "player_age", "", 60),
      player_sex: setupValueText(formData, "player_sex", "", 80),
      previous_life_age: includeFormerLife ? textField(formData, "previous_life_age", "", 60) : "",
      previous_life_sex: includeFormerLife ? setupValueText(formData, "previous_life_sex", "", 80) : "",
      backstory_mode: setupValueText(formData, "backstory_mode", "known", 60),
      memory_policy: setupValueText(formData, "memory_policy", "known", 80),
      character_backstory: textField(formData, "character_backstory", "", 1600),
      hair: textField(formData, "hair", "", 120),
      facial_features: textField(formData, "facial_features", "", 300),
      appearance: textField(formData, "appearance", "", 400),
      starter_equipment: textField(formData, "starter_equipment", "", 500),
      difficulty: setupValueText(formData, "difficulty", "normal", 60),
      narration_detail: setupValueText(formData, "narration_detail", "rich", 120),
      world_style: readListSetting(formData, "world_style", "frontier dark fantasy"),
      custom_style: textField(formData, "custom_style", "", 800),
      start_location: textField(formData, "start_location", "Mosswake Gate", 100),
      leveling_system: boolField(formData, "leveling_system"),
      game_system: boolField(formData, "game_system"),
      system_style: setupValueText(formData, "system_style", "subtle blue-window system", 120),
      special_ability_origin: specialAbilityOrigin,
      special_abilities: specialAbilities,
      special_ability: specialAbilities.length > 0,
      special_ability_locked: specialAbilities[0]?.locked || false,
      special_ability_name: specialAbilities[0]?.name || "",
      special_ability_description: specialAbilities[0]?.description || "",
      skill_style: skillCustom ? "custom" : setupValueText(formData, "skill_style", "standard", 60),
      proficiency_system: boolField(formData, "proficiency_system"),
      proficiency_access: setupValueText(formData, "proficiency_access", "learned", 80),
      skill_levels_enabled: boolField(formData, "skill_levels_enabled"),
      new_skill_frequency: setupValueText(formData, "new_skill_frequency", "normal", 80),
      skill_growth_speed: skillGain.speed,
      proficiency_growth_speed: proficiencyGain.speed,
      xp_growth_speed: xpGain.speed,
      skill_growth_multiplier: skillGain.multiplier,
      proficiency_growth_multiplier: proficiencyGain.multiplier,
      xp_growth_multiplier: xpGain.multiplier,
      skill_growth_note: skillGain.note,
      proficiency_growth_note: proficiencyGain.note,
      xp_growth_note: xpGain.note,
      custom_skills: customSkills,
      death_rules: setupValueText(formData, "death_rules", "downed, not deleted", 80),
      npc_stat_scaling: setupValueText(formData, "npc_stat_scaling", "relative ranks", 80),
      npc_skill_frequency: setupValueText(formData, "npc_skill_frequency", "some trained NPCs", 100),
      rank_scale: setupValueText(formData, "rank_scale", "F,E,D,C,B,A,S,SS,SSS", 100),
      economy: readListSetting(formData, "economy", "scarce"),
      loot_rarity: setupValueText(formData, "loot_rarity", "earned and uncommon", 80),
      inventory_weight_limit: intField(formData, "inventory_weight_limit", 60, 1, 100000),
      inventory_slot_limit: intField(formData, "inventory_slot_limit", 24, 1, 10000),
      inventory_rules: textField(formData, "inventory_rules", "", 900),
      magic_level: setupValueText(formData, "magic_level", "rare", 80),
      world_races: readListSetting(formData, "world_races", "human"),
      race_magic_enabled: boolField(formData, "race_magic_enabled"),
      race_magic_rarity: setupValueText(formData, "race_magic_rarity", "same as world magic", 100),
      race_magic_rules: textField(formData, "race_magic_rules", "", 1200),
      race_ability_rules: textField(formData, "race_ability_rules", "", 1200),
      tech_level: setupValueText(formData, "tech_level", "iron age", 80),
      tone: setupValueText(formData, "tone", "grounded adventure", 100),
      npc_density: setupValueText(formData, "npc_density", "moderate", 80),
      quest_style: readListSetting(formData, "quest_style", "emergent"),
      faction_pressure: readListSetting(formData, "faction_pressure", "local disputes"),
    };
    // Prefer last Randomize compile; otherwise soft-compile idea box / world_style for session bias.
    let themeForSession = lastSessionTheme && typeof lastSessionTheme === "object" ? { ...lastSessionTheme } : null;
    if (!themeForSession || !Object.keys(themeForSession).length) {
      const ideaBox = setupRandomizeIdea();
      const seed = ideaBox || String(setupPayload.world_style || "");
      if (seed) {
        try {
          const composed = await composeSetupIntent(seed);
          themeForSession = composed.session_theme ? { ...composed.session_theme } : null;
        } catch {
          themeForSession = null;
        }
      }
    }
    // Preserve manual session theme_model from Model modal even if we recompiled intent.
    const manualThemeModel = currentSessionThemeModel();
    if (manualThemeModel) {
      themeForSession = { ...(themeForSession || {}), theme_model: manualThemeModel };
      lastSessionTheme = themeForSession;
    }
    setupPayload.session_theme = themeForSession && typeof themeForSession === "object" ? themeForSession : {};
    const response = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(setupPayload),
    });
    if (!response.ok) throw new Error(await response.text());
    latestInput.innerHTML = "";
    const responsePayload = await response.json();
    if (!displayTurnPayload(responsePayload, { animateNarration: true, startSplash: true })) {
      hideStartSplash();
      renderShell(responsePayload);
      await requestTurn("", { displayText: "Opening scene" });
    }
  }, startLabel), startLabel).catch((error) => {
    hideStartSplash();
    latestOutput.innerHTML = `<p class="bad">Could not start playthrough: ${escapeHtml(error.message || String(error))}</p>`;
  });
}

async function submitTurn(event) {
  event.preventDefault();
  if (aiBusy) return;
  const text = turnInput.value.trim();
  await enqueueAiTask(async () => {
    try {
      await requestTurn(text);
    } catch (error) {
      latestOutput.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    }
  }, text ? "AI is writing the turn..." : "AI is continuing...");
  turnInput.focus();
}

async function saveAlias(event) {
  event.preventDefault();
  if (!selectedEntity) return;
  const alias = aliasInput.value.trim();
  if (!alias) return;
  const response = await fetch("/api/alias", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      alias,
      entity_type: selectedEntity.type,
      entity_code: selectedEntity.entity.code,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  renderShell(await response.json());
  aliasInput.value = "";
}

async function createPlayerAlias(form) {
  const alias = form.querySelector('[name="alias"]')?.value.trim() || "";
  const notes = form.querySelector('[name="notes"]')?.value.trim() || "";
  if (!alias) return;
  const response = await fetch("/api/player-alias", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alias, notes }),
  });
  if (!response.ok) throw new Error(await response.text());
  renderShell(await response.json());
}

async function updatePlayerAliasState(payload) {
  const response = await fetch("/api/player-alias/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  renderShell(await response.json());
}

async function rewindTurn(snapshotId = null) {
  const options = snapshotId
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ snapshot_id: Number(snapshotId) }),
      }
    : { method: "POST" };
  const response = await fetch("/api/rewind", options);
  if (!response.ok) throw new Error(await response.text());
  latestInput.innerHTML = "";
  latestOutput.innerHTML = paragraphs("Rewound one turn.");
  renderShell(await response.json());
}

async function regenerateTurn() {
  latestInput.innerHTML = paragraphs("Regenerate last response");
  showTurnWaitPanel("Regenerating response", "regenerate");
  clearSuggestions();
  let payload = null;
  try {
    const response = await fetch("/api/regenerate", { method: "POST" });
    if (!response.ok) throw new Error(await response.text());
    payload = await response.json();
  } finally {
    clearTurnWaitTimer();
  }
  if (!displayTurnPayload(payload, { animateNarration: true })) throw new Error("Regenerated response did not include narration.");
}

async function exportWorld() {
  const response = await fetch("/api/export");
  if (!response.ok) throw new Error(await response.text());
  const blob = new Blob([JSON.stringify(await response.json(), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ai-rpg-world-${Date.now()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

async function importWorld(file) {
  const data = JSON.parse(await file.text());
  const response = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await response.text());
  latestInput.innerHTML = "";
  latestOutput.innerHTML = paragraphs("World imported.");
  renderShell(await response.json());
}

async function runSearch(query) {
  const response = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error(await response.text());
  searchResults = await response.json();
  renderIndex();
}

["beforeinput", "input", "change", "click", "keydown", "pointerdown", "submit"].forEach((eventName) => {
  setupForm.addEventListener(
    eventName,
    (event) => {
      if (!setupRandomizationLocked()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    },
    true,
  );
});

setupForm.addEventListener("change", (event) => {
  if (event.target.matches("[data-lock-setting]")) return;
  const select = event.target.closest("select[name]");
  if (select?.value === "random") {
    const label = `Randomizing ${select.name}...`;
    enqueueAiTask(
      withSetupRandomizationLock(
        () => randomizeField(select.name),
        label,
        (error) => {
          fallbackRandomizeField(select.name);
          latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
        },
        { updateConditionals: true },
      ),
      label,
    );
    return;
  }
  const randomList = event.target.closest('input[type="checkbox"][value="random"]');
  if (randomList?.checked) {
    const label = `Randomizing ${randomList.name}...`;
    enqueueAiTask(
      withSetupRandomizationLock(
        () => randomizeField(randomList.name),
        label,
        (error) => {
          fallbackRandomizeField(randomList.name);
          latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
        },
        { updateConditionals: true },
      ),
      label,
    );
    return;
  }
  updateConditionalSetup();
});
setupForm.addEventListener("input", (event) => {
  if (event.target.matches("[data-gain-slider]")) {
    const name = event.target.dataset.gainSlider;
    const number = setupForm.querySelector(`[data-gain-number="${name}"]`);
    if (number) number.value = Number(event.target.value).toFixed(2);
    updateGainControls();
  }
  if (event.target.matches("[data-gain-number]")) {
    const name = event.target.dataset.gainNumber;
    const slider = setupForm.querySelector(`[data-gain-slider="${name}"]`);
    const value = Math.max(0, Math.min(100, Number(event.target.value || 0)));
    if (slider) slider.value = String(Math.min(Number(slider.max || 10), Math.max(Number(slider.min || 0), value)));
    updateGainControls();
  }
  if (event.target.matches('textarea[name="character_backstory"], [data-custom-input="backstory_mode"], [data-custom-input="memory_policy"]')) updateConditionalSetup();
});
turnInput?.addEventListener("input", updateComposerState);
setupForm.addEventListener("click", (event) => {
  const textAiOpen = event.target.closest("[data-text-ai-open]");
  if (textAiOpen) {
    event.preventDefault();
    const wrapper = textAiOpen.closest(".textAiWrap");
    const panel = wrapper?.nextElementSibling?.matches("[data-text-ai-panel]") ? wrapper.nextElementSibling : null;
    if (!wrapper || !panel) return;
    const willOpen = !panel.classList.contains("open");
    closeTextAiPanels(willOpen ? panel : null);
    panel.classList.toggle("open", willOpen);
    panel.classList.toggle("hidden", !willOpen);
    if (willOpen) panel.querySelector("[data-text-ai-prompt]")?.focus();
    updateTextAiControls();
    return;
  }
  const textAiClose = event.target.closest("[data-text-ai-close]");
  if (textAiClose) {
    event.preventDefault();
    const panel = textAiClose.closest("[data-text-ai-panel]");
    panel?.classList.remove("open");
    panel?.classList.add("hidden");
    updateTextAiControls();
    return;
  }
  const textAiFill = event.target.closest("[data-text-ai-fill]");
  if (textAiFill) {
    event.preventDefault();
    const panel = textAiFill.closest("[data-text-ai-panel]");
    const control = panel?.previousElementSibling?.querySelector("[data-text-ai-control]");
    if (!panel || !control) return;
    textAiFill.disabled = true;
    const label = `Filling ${textAiLabel(control)}...`;
    enqueueAiTask(withSetupRandomizationLock(() => fillTextAiControl(control, panel), label), label)
      .catch((error) => {
        latestOutput.innerHTML = `<p class="bad">Could not fill text: ${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        textAiFill.disabled = false;
        updateTextAiControls();
      });
    return;
  }
  const fieldRandomizer = event.target.closest("[data-randomize-field]");
  if (fieldRandomizer) {
    event.preventDefault();
    const name = fieldRandomizer.dataset.randomizeField;
    fieldRandomizer.disabled = true;
    const label = `Randomizing ${name}...`;
    enqueueAiTask(
      withSetupRandomizationLock(
        () => randomizeField(name, { ignoreLock: true }),
        label,
        (error) => {
          fallbackRandomizeField(name, { ignoreLock: true });
          latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
        },
      ),
      label,
    )
      .finally(() => {
        fieldRandomizer.disabled = false;
      });
    return;
  }
  const randomizer = event.target.closest("[data-randomize-group]");
  if (randomizer) {
    randomizer.disabled = true;
    const label = `Randomizing ${randomizer.dataset.randomizeGroup}...`;
    const group = randomizer.dataset.randomizeGroup;
    enqueueAiTask(
      withSetupRandomizationLock(
        () => randomizeGroup(group),
        label,
        (error) => {
          fallbackRandomizeSequence(RANDOM_GROUPS[group] || []);
          latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
        },
      ),
      label,
    )
      .finally(() => {
        randomizer.disabled = false;
      });
  }
  const removeAbility = event.target.closest(".removeAbility");
  if (removeAbility) removeAbility.closest(".abilitySetupCard")?.remove();
  const randomizeOne = event.target.closest(".randomizeOneAbility");
  if (randomizeOne) {
    const card = randomizeOne.closest(".abilitySetupCard");
    const preset = randomAbilityPreset();
    if (card) {
      card.outerHTML = abilityTemplate(preset);
      ensureTextAiControls(abilityList);
      decorateFunctionHelp(abilityList);
    }
  }
  const addAfter = event.target.closest(".addAbilityAfter");
  if (addAfter) {
    addAfter.closest(".abilitySetupCard")?.insertAdjacentHTML("afterend", abilityTemplate());
    ensureTextAiControls(abilityList);
    decorateFunctionHelp(abilityList);
  }
});
setupForm.addEventListener("submit", startGame);
setupForm.addEventListener("blur", (event) => {
  if (event.target?.name === "custom_skills") event.target.value = commaSeparatedPhrases(event.target.value);
}, true);
saveSetupSettingsButton?.addEventListener("click", () => {
  try {
    saveSetupSettings();
  } catch (error) {
    window.alert(error.message || String(error));
  }
});
setupSettingsFile?.addEventListener("change", () => {
  const file = setupSettingsFile.files?.[0];
  if (!file) return;
  loadSetupSettings(file)
    .catch((error) => window.alert(error.message || String(error)))
    .finally(() => {
      setupSettingsFile.value = "";
    });
});
randomizeSetup?.addEventListener("click", () => {
  randomizeSetup.disabled = true;
  const idea = setupRandomizeIdea();
  const label = idea ? "Randomizing setup from your idea..." : "Randomizing setup...";
  const promptInput = document.querySelector("#randomizeSetupPrompt");
  if (promptInput) promptInput.disabled = true;
  enqueueAiTask(
    withSetupRandomizationLock(
      () => randomizeAllSetup({ idea }),
      label,
      (error) => {
        fallbackRandomizeSequence(RANDOM_FIELD_ORDER);
        latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
      },
    ),
    label,
  )
    .finally(() => {
      randomizeSetup.disabled = false;
      if (promptInput) promptInput.disabled = false;
    });
});
document.querySelector("#randomizeSetupPrompt")?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  randomizeSetup?.click();
});
document.querySelector("#directorPresets")?.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-director-preset]");
  if (!btn) return;
  applyDirectorPreset(btn.dataset.directorPreset, { runRandomize: true });
});
addAbilityButton?.addEventListener("click", () => addAbility());
randomAbilityButton?.addEventListener("click", () => {
  randomAbilityButton.disabled = true;
  const label = "Randomizing abilities...";
  enqueueAiTask(
    withSetupRandomizationLock(
      () => randomizeField("special_abilities", { ignoreLock: true }),
      label,
      (error) => {
        fallbackRandomizeField("special_abilities", { ignoreLock: true });
        latestOutput.innerHTML = paragraphs(`Model randomizer unavailable; used local fallback. ${error.message || error}`);
      },
    ),
    label,
  )
    .finally(() => {
      randomAbilityButton.disabled = false;
        updateAbilityOriginControls();
    });
});
setupPrevButton?.addEventListener("click", () => setSetupStep(setupStep - 1));
setupNextButton?.addEventListener("click", () => {
  if (setupStep === setupSections.length - 1) {
    setupForm.requestSubmit();
    return;
  }
  setSetupStep(setupStep + 1);
});
setupStepButtons.forEach((button) => button.addEventListener("click", () => setSetupStep(Number(button.dataset.setupStep))));
turnForm.addEventListener("submit", submitTurn);
continueButton?.addEventListener("click", () => {
  if (aiBusy) return;
  enqueueAiTask(() => requestTurn(""), "AI is continuing...").catch((error) => {
    latestOutput.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
});
suggestButton?.addEventListener("click", () => {
  if (aiBusy) return;
  enqueueAiTask(() => requestSuggestions(), "AI is suggesting inputs...").catch((error) => {
    suggestionPanel?.classList.remove("hidden");
    if (suggestionsEl) suggestionsEl.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
});
regenSuggestionsButton?.addEventListener("click", () => {
  if (aiBusy) return;
  enqueueAiTask(() => requestSuggestions(suggestionInstruction?.value || ""), "AI is regenerating inputs...").catch((error) => {
    suggestionPanel?.classList.remove("hidden");
    if (suggestionsEl) suggestionsEl.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
});
suggestionInstruction?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || aiBusy) return;
  event.preventDefault();
  enqueueAiTask(() => requestSuggestions(suggestionInstruction.value), "AI is regenerating inputs...").catch((error) => {
    suggestionPanel?.classList.remove("hidden");
    if (suggestionsEl) suggestionsEl.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
});
refreshButton.addEventListener("click", () => loadState().catch((error) => (latestOutput.innerHTML = paragraphs(error.message))));
regenerateButton?.addEventListener("click", () => {
  if (aiBusy) return;
  enqueueAiTask(() => regenerateTurn(), "AI is regenerating...").catch((error) => {
    latestOutput.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
});
rewindButton.addEventListener("click", () => rewindTurn().catch((error) => (latestOutput.innerHTML = paragraphs(error.message))));
exportButton.addEventListener("click", () => exportWorld().catch((error) => (latestOutput.innerHTML = paragraphs(error.message))));
importButton.addEventListener("click", () => importFile.click());
saveSlotButton?.addEventListener("click", () => {
  saveCampaignSlotPrompt().catch((error) => (latestOutput.innerHTML = paragraphs(error.message || String(error))));
});
loadSlotButton?.addEventListener("click", () => {
  loadCampaignSlotPrompt().catch((error) => (latestOutput.innerHTML = paragraphs(error.message || String(error))));
});
compactModeButton?.addEventListener("click", () => {
  applyCompactMode(!document.body.classList.contains("compact-mode"));
});
document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.id === "consolidateMemoryButton") {
    const statusEl = document.querySelector("#contextHealthStatus");
    consolidateMemoryNow(statusEl).catch((error) => {
      if (statusEl) statusEl.textContent = error.message || String(error);
      latestOutput.innerHTML = paragraphs(error.message || String(error));
    });
  }
  if (target.id === "refreshHealthButton") {
    loadState().catch((error) => (latestOutput.innerHTML = paragraphs(error.message || String(error))));
  }
});
applyCompactMode(isCompactModeEnabled());
async function openModelModalFromUi() {
  if (modelModalToggle) modelModalToggle.checked = true;
  modelModal?.classList.remove("hidden");
  // Always load live settings content when opened from UI.
  await openModelModal();
}

function closeModelModalFromUi() {
  if (modelModalToggle) modelModalToggle.checked = false;
  modelModal?.classList.add("hidden");
}

// Keep checkbox + .hidden class in sync (labels still use for=modelModalToggle).
modelModalToggle?.addEventListener("change", () => {
  if (modelModalToggle.checked) {
    modelModal?.classList.remove("hidden");
    openModelModal().catch((error) => {
      if (modelModalContent) {
        modelModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      }
    });
  } else {
    modelModal?.classList.add("hidden");
  }
});

setupModelButton?.addEventListener("click", (event) => {
  // Label would toggle checkbox; open explicitly so content loads.
  event.preventDefault();
  openModelModalFromUi().catch((error) => {
    if (modelModalContent) {
      modelModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    }
  });
});
closeModelModal?.addEventListener("click", (event) => {
  event.preventDefault();
  closeModelModalFromUi();
});
modelModal?.addEventListener("click", (event) => {
  if (event.target === modelModal) closeModelModalFromUi();
});
modelButton?.addEventListener("click", () => {
  // In play: open full LLM modal (not only the side tab)
  openModelModalFromUi().catch((error) => {
    if (modelModalContent) {
      modelModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    }
  });
});
importFile.addEventListener("change", () => {
  const file = importFile.files?.[0];
  if (file) importWorld(file).catch((error) => (latestOutput.innerHTML = paragraphs(error.message)));
  importFile.value = "";
});
newGameButton.addEventListener("click", () => {
  if (window.confirm("Return to the main menu?")) {
    showMainMenu();
  }
});
closeEntityMenu.addEventListener("click", () => entityMenu.classList.add("hidden"));
insertEntityRef.addEventListener("click", () => {
  if (selectedEntity) insertRef(selectedEntity.type, selectedEntity.entity.code);
});
aliasForm.addEventListener("submit", (event) => {
  saveAlias(event).catch((error) => (entityBody.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`));
});

document.addEventListener("pointerover", (event) => {
  const helpTarget = event.target.closest("[data-help-text]");
  if (helpTarget) showHelpForTarget(helpTarget);
});

document.addEventListener("pointerout", (event) => {
  const helpTarget = event.target.closest("[data-help-text]");
  if (!helpTarget || helpTarget.contains(event.relatedTarget) || pinnedHelpTarget === helpTarget) return;
  hideHelpTooltip({ force: true });
});

document.addEventListener("focusin", (event) => {
  const helpTarget = event.target.closest("[data-help-text]");
  if (helpTarget) showHelpForTarget(helpTarget);
});

document.addEventListener("focusout", (event) => {
  const helpTarget = event.target.closest("[data-help-text]");
  if (!helpTarget || pinnedHelpTarget === helpTarget) return;
  hideHelpTooltip({ force: true });
});

document.addEventListener("click", (event) => {
  const helpTarget = event.target.closest("[data-help-text]");
  const actionTarget = helpTarget?.matches("button, input, select, textarea, a, label, .buttonLike") || helpTarget?.closest("button, a, label, .buttonLike");
  if (helpTarget && !actionTarget) {
    toggleHelpPopover(helpTarget);
  } else if (!event.target.closest(".globalHelpTooltip")) {
    closeHelpPopovers();
  }

  const suggestion = event.target.closest(".useSuggestionButton");
  if (suggestion) {
    turnInput.value = suggestion.dataset.suggestion || suggestion.textContent || "";
    clearSuggestions({ keepInstruction: true });
    updateComposerState();
    turnInput.focus();
    return;
  }
  const rewindPoint = event.target.closest(".rewindPointButton");
  if (rewindPoint) {
    rewindTurn(rewindPoint.dataset.snapshotId).catch((error) => (latestOutput.innerHTML = paragraphs(error.message)));
    return;
  }
  const link = event.target.closest(".entityLink");
  if (link) {
    showEntity(link.dataset.code);
    return;
  }
  const insert = event.target.closest(".insertRefButton");
  if (insert) insertRef(insert.dataset.type, insert.dataset.code);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeHelpPopovers();
});

indexTabs?.addEventListener("click", (event) => {
  const popWin = event.target.closest("[data-popout-window]");
  if (popWin) {
    event.preventDefault();
    event.stopPropagation();
    openTabPopout(popWin.getAttribute("data-popout-window") || "player", "window");
    return;
  }
  const pop = event.target.closest("[data-popout]");
  if (pop) {
    event.preventDefault();
    event.stopPropagation();
    openTabPopout(pop.getAttribute("data-popout") || pop.dataset.popout, "float");
    return;
  }
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  setActiveTab(button.dataset.tab);
});

indexContent.addEventListener("click", (event) => {
  const popWin = event.target.closest("[data-popout-window]");
  if (popWin) {
    event.preventDefault();
    openTabPopout(popWin.getAttribute("data-popout-window") || "player", "window");
    return;
  }
  const pop = event.target.closest("[data-popout]");
  if (pop) {
    event.preventDefault();
    openTabPopout(pop.getAttribute("data-popout") || "player", "float");
    return;
  }
  const playerArt = event.target.closest("[data-player-portrait-regen], #playerPortraitRegen");
  if (playerArt) {
    event.preventDefault();
    const kind = document.querySelector("#playerArtGenKind")?.value || playerArt.getAttribute("data-player-art-kind") || "both";
    regeneratePlayerPortrait(kind);
  }
});

document.querySelector("#mapFocusChatBtn")?.addEventListener("click", () => {
  setSceneFocus(true, { scroll: true, focusInput: true });
});
document.querySelector("#sceneFocusMapBtn")?.addEventListener("click", () => {
  setSceneFocus(false, { scroll: false });
  document.querySelector("#mapMain")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

historyEl.addEventListener("click", (event) => {
  const pageButton = event.target.closest("button[data-history-page]");
  if (!pageButton) return;
  const groups = historyGroups();
  const pageCount = Math.max(1, Math.ceil(groups.length / HISTORY_PAGE_SIZE));
  if (pageButton.dataset.historyPage === "prev") historyPage = Math.max(0, historyPage - 1);
  if (pageButton.dataset.historyPage === "next") historyPage = Math.min(pageCount - 1, historyPage + 1);
  renderHistory();
});

historyEl.addEventListener("toggle", (event) => {
  const details = event.target.closest("details[data-history-key]");
  if (!details) return;
  const openState = historyOpenState();
  openState[details.dataset.historyKey] = details.open;
  saveHistoryOpenState(openState);
}, true);

indexContent.addEventListener("submit", (event) => {
  const playerAliasForm = event.target.closest("#playerAliasForm");
  if (playerAliasForm) {
    event.preventDefault();
    createPlayerAlias(playerAliasForm).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
    return;
  }
  const playerAliasStateForm = event.target.closest(".playerAliasStateForm");
  if (playerAliasStateForm) {
    event.preventDefault();
    updatePlayerAliasState({
      alias_id: Number(playerAliasStateForm.dataset.playerAliasId),
      disguised: Boolean(playerAliasStateForm.querySelector('[name="disguised"]')?.checked),
      disguise_description: playerAliasStateForm.querySelector('[name="disguise_description"]')?.value.trim() || "",
    }).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
    return;
  }
  const modelForm = event.target.closest("#modelForm");
  if (modelForm) {
    event.preventDefault();
    saveModelConfig(modelForm).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
    return;
  }
  const form = event.target.closest("#searchForm");
  if (!form) return;
  event.preventDefault();
  const query = form.querySelector("#searchInput")?.value.trim();
  if (query) runSearch(query).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
});

indexContent.addEventListener("click", (event) => {
  const activateAlias = event.target.closest(".playerAliasActivate");
  if (activateAlias) {
    updatePlayerAliasState({ alias_id: Number(activateAlias.dataset.playerAliasId), active: true }).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
    return;
  }
  const deactivateAlias = event.target.closest(".playerAliasDeactivate");
  if (deactivateAlias) {
    updatePlayerAliasState({ alias_id: null }).catch((error) => (indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message)}</p>`));
    return;
  }
  const testConnection = event.target.closest(".testModelConnection");
  if (testConnection) {
    testConnection.disabled = true;
    testModelConnection(indexContent)
      .catch((error) => {
        indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        testConnection.disabled = false;
      });
    return;
  }
  const selectFile = event.target.closest(".selectModelFile");
  if (!selectFile) return;
  const form = selectFile.closest("#modelForm");
  if (!form) return;
  selectFile.disabled = true;
  selectModelFile(form)
    .catch((error) => {
      indexContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    })
    .finally(() => {
      selectFile.disabled = false;
    });
});

modelModalContent?.addEventListener("submit", (event) => {
  const modelForm = event.target.closest("#modelForm");
  if (modelForm) {
    event.preventDefault();
    saveModelConfig(modelForm).catch((error) => {
      modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    });
    return;
  }
  const imageForm = event.target.closest("#imageForm");
  if (imageForm) {
    event.preventDefault();
    saveImageConfig(imageForm, { rerender: true, statusMessage: "Image settings saved." }).catch((error) => {
      modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    });
  }
});

modelModalContent?.addEventListener("click", (event) => {
  const testConnection = event.target.closest(".testModelConnection");
  if (testConnection) {
    testConnection.disabled = true;
    testModelConnection(modelModalContent)
      .catch((error) => {
        modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        testConnection.disabled = false;
      });
    return;
  }
  const testLock = event.target.closest(".testCharacterLock");
  if (testLock) {
    testLock.disabled = true;
    testCharacterLockStack(modelModalContent?.querySelector?.("[data-character-lock-status]"))
      .catch((error) => {
        const st = modelModalContent?.querySelector?.("[data-character-lock-status]");
        if (st) {
          st.hidden = false;
          st.classList.add("bad");
          st.textContent = error.message || String(error);
        }
      })
      .finally(() => {
        testLock.disabled = false;
      });
    return;
  }
  const testImage = event.target.closest(".testImageConnection");
  if (testImage) {
    testImage.disabled = true;
    testImageConnection(modelModalContent)
      .catch((error) => {
        modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        testImage.disabled = false;
      });
    return;
  }
  const readinessBtn = event.target.closest(".checkImageReadiness");
  if (readinessBtn) {
    readinessBtn.disabled = true;
    checkImageReadiness(modelModalContent)
      .catch((error) => {
        modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        readinessBtn.disabled = false;
      });
    return;
  }
  const launchBtn = event.target.closest(".launchImageBackend");
  if (launchBtn) {
    event.preventDefault();
    event.stopPropagation();
    launchBtn.disabled = true;
    launchImageBackendFromUi(modelModalContent, event)
      .catch((error) => {
        const status = modelModalContent?.querySelector?.("[data-image-status]");
        if (status) status.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
        else if (modelModalContent) {
          modelModalContent.insertAdjacentHTML(
            "beforeend",
            `<p class="bad">${escapeHtml(error.message || String(error))}</p>`,
          );
        }
      })
      .finally(() => {
        launchBtn.disabled = false;
      });
    return;
  }
  const searchBtn = event.target.closest(".allowSearchRoot");
  if (searchBtn) {
    const kind = searchBtn.dataset.searchKind || "forge";
    const form = searchBtn.closest("#imageForm");
    searchBtn.disabled = true;
    searchImageBackendRoot(kind, form)
      .catch((error) => {
        modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        searchBtn.disabled = false;
      });
    return;
  }
  const browseBtn = event.target.closest(".browseBackendRoot");
  if (browseBtn) {
    const kind = browseBtn.dataset.browseKind || "forge";
    const form = browseBtn.closest("#imageForm");
    browseBtn.disabled = true;
    browseBackendRoot(kind, form)
      .catch((error) => {
        const status = modelModalContent?.querySelector?.("[data-image-status]");
        if (status) status.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
        else if (modelModalContent) {
          modelModalContent.insertAdjacentHTML(
            "beforeend",
            `<p class="bad">${escapeHtml(error.message || String(error))}</p>`,
          );
        }
      })
      .finally(() => {
        browseBtn.disabled = false;
      });
    return;
  }
  const imageTab = event.target.closest("[data-image-tab]");
  if (imageTab && modelModalContent?.contains(imageTab)) {
    imageSettingsTab = imageTab.dataset.imageTab || "general";
    // Preserve in-progress form values by reading then re-render is heavy; just toggle panels.
    modelModalContent.querySelectorAll(".imageSettingsTab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.imageTab === imageSettingsTab);
    });
    modelModalContent.querySelectorAll(".imageTabPanel").forEach((panel) => {
      panel.classList.toggle("open", panel.dataset.imagePanel === imageSettingsTab);
    });
    if (imageSettingsTab === "installs") {
      refreshImageInstallablesPanel(modelModalContent).catch(() => {});
    }
    return;
  }
  const refreshInstalls = event.target.closest(".refreshImageInstallables");
  if (refreshInstalls && modelModalContent?.contains(refreshInstalls)) {
    event.preventDefault();
    refreshInstalls.disabled = true;
    refreshImageInstallablesPanel(modelModalContent)
      .catch(() => {})
      .finally(() => {
        refreshInstalls.disabled = false;
      });
    return;
  }
  const installBtn = event.target.closest(".installImageComponent");
  if (installBtn && modelModalContent?.contains(installBtn)) {
    event.preventDefault();
    const id = installBtn.getAttribute("data-install-id") || "";
    if (!id) return;
    installBtn.disabled = true;
    const status = modelModalContent.querySelector("[data-image-status]");
    if (status) {
      status.innerHTML = `<p class="empty">Installing <code>${escapeHtml(id)}</code>… large models can take several minutes.</p>`;
    }
    fetch("/api/image-installables/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail || data.error || "Install failed";
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        const host = modelModalContent.querySelector("[data-image-installables]");
        if (host) host.innerHTML = renderImageInstallablesHtml(data);
        if (status) {
          status.innerHTML = `<p class="good">Installed <code>${escapeHtml(id)}</code>${data.install?.already ? " (already present)" : ""}.</p>`;
        }
      })
      .catch((error) => {
        if (status) status.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
      })
      .finally(() => {
        installBtn.disabled = false;
      });
    return;
  }
  const refreshCatalog = event.target.closest(".refreshImageCatalog");
  if (refreshCatalog) {
    const form = modelModalContent.querySelector("#imageForm");
    const provider = form?.querySelector('[name="provider"]')?.value || imageConfig?.provider || "off";
    refreshCatalog.disabled = true;
    const status = modelModalContent.querySelector("[data-image-status]");
    if (status) status.innerHTML = `<p class="empty">Refreshing catalog from ${escapeHtml(provider)}…</p>`;
    // Save URL fields first so catalog hits the right host
    if (form) {
      saveImageConfig(form, { rerender: false })
        .then(() => loadImageCatalog(provider))
        .then(() => {
          modelModalContent.innerHTML = `${renderModelForm()}<p class="good">Catalog refreshed.</p>`;
          decorateFunctionHelp(modelModalContent);
        })
        .catch((error) => {
          if (status) status.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
        })
        .finally(() => {
          refreshCatalog.disabled = false;
        });
    } else {
      loadImageCatalog(provider)
        .then(() => {
          modelModalContent.innerHTML = `${renderModelForm()}<p class="good">Catalog refreshed.</p>`;
          decorateFunctionHelp(modelModalContent);
        })
        .finally(() => {
          refreshCatalog.disabled = false;
        });
    }
    return;
  }
  const selectFile = event.target.closest(".selectModelFile");
  if (!selectFile) return;
  const form = selectFile.closest("#modelForm");
  if (!form) return;
  selectFile.disabled = true;
  selectModelFile(form)
    .catch((error) => {
      modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    })
    .finally(() => {
      selectFile.disabled = false;
    });
});

document.addEventListener("click", (event) => {
  const backendTab = event.target.closest("[data-art-backend]");
  if (backendTab) {
    event.preventDefault();
    setSetupArtBackendTab(backendTab.getAttribute("data-art-backend") || "forge");
    // Refresh catalog for the chosen backend when switching
    refreshSetupArtCatalog().catch(() => {});
    return;
  }
  const promptTab = event.target.closest("[data-art-prompt-tab]");
  if (promptTab) {
    event.preventDefault();
    setArtPromptTab(promptTab.getAttribute("data-art-prompt-tab") || "face");
    return;
  }
  // Clicking a preview frame selects that image's prompt tab.
  if (event.target.closest("[data-setup-face]")) {
    setArtPromptTab("face");
  } else if (event.target.closest("[data-setup-fullbody]")) {
    setArtPromptTab("fullbody");
  }
  const clearBtn = event.target.closest("[data-art-clear], .artClearBtn");
  if (clearBtn) {
    event.preventDefault();
    event.stopPropagation();
    const slot =
      clearBtn.getAttribute("data-art-clear") ||
      clearBtn.closest("[data-art-slot]")?.getAttribute("data-art-slot") ||
      (clearBtn.closest("[data-setup-face]") ? "face" : "") ||
      (clearBtn.closest("[data-setup-fullbody]") ? "fullbody" : "") ||
      "";
    if (slot) clearArtSlot(slot);
    return;
  }
  if (event.target.closest("#setupArtRebuildBtn")) {
    event.preventDefault();
    rebuildEnginePrompts({ force: true }).catch(() => {});
    return;
  }
  if (event.target.closest("#setupArtLockTestBtn")) {
    event.preventDefault();
    const btn = event.target.closest("#setupArtLockTestBtn");
    btn.disabled = true;
    testCharacterLockStack(document.querySelector("#setupArtLockStatus"))
      .catch(() => {})
      .finally(() => {
        btn.disabled = false;
      });
    return;
  }
  if (event.target.closest("#portraitPreviewBtn, [data-art-generate]")) {
    event.preventDefault();
    // Setup: only the selected Face / Full body tab (never both in one click).
    const genKind = activeArtPromptTab === "fullbody" ? "fullbody" : "face";
    const faceP = document.querySelector("#setupArtFacePrompt")?.value?.trim();
    const bodyP = document.querySelector("#setupArtBodyPrompt")?.value?.trim();
    const faceN = document.querySelector("#setupArtFaceNegative")?.value?.trim();
    const bodyN = document.querySelector("#setupArtBodyNegative")?.value?.trim();
    if (genKind === "face" && (!faceP || !faceN)) {
      setSetupArtStatus(
        "Face positive/negative empty. Select Face tab, Rebuild prompts, then Generate.",
        { bad: true },
      );
      return;
    }
    if (genKind === "fullbody" && (!bodyP || !bodyN)) {
      setSetupArtStatus(
        "Full-body positive/negative empty. Select Full body tab, Rebuild prompts, then Generate.",
        { bad: true },
      );
      return;
    }
    generateSetupPortrait(genKind).catch((err) => {
      setSetupArtStatus(err?.message || String(err) || "Art failed", { bad: true });
    });
    return;
  }
  if (event.target.closest("#studioGenerateBtn")) {
    event.preventDefault();
    const genKind = document.querySelector("#studioArtGenKind")?.value || activeArtPromptTab || "face";
    generateSetupPortrait(genKind).catch((err) => {
      setSetupArtStatus(err?.message || String(err) || "Art failed", { bad: true });
      const st = document.querySelector("#studioStatus");
      if (st) st.textContent = err?.message || String(err) || "Art failed";
    });
    return;
  }
  const artKind = event.target.closest("[data-art-kind]");
  if (artKind) {
    event.preventDefault();
    const kind = artKind.getAttribute("data-art-kind") || "both";
    generateSetupPortrait(kind).catch((err) => {
      setSetupArtStatus(err?.message || String(err) || "Art failed", { bad: true });
    });
    return;
  }
  if (event.target.closest("#setupArtGuideDismiss")) {
    event.preventDefault();
    dismissSetupArtGuide();
    return;
  }
  if (event.target.closest("#setupArtGuideShow")) {
    event.preventDefault();
    showSetupArtGuide({ force: true });
    return;
  }
  if (event.target.closest("#openImageStudioBtn, [data-open-image-studio]")) {
    event.preventDefault();
    openImageStudio("float").catch((err) => {
      setSetupArtStatus?.(err?.message || String(err), { bad: true });
    });
    return;
  }
  if (event.target.closest("#openImageBrowserBtn, [data-open-image-browser]")) {
    event.preventDefault();
    openImageBrowser("float").catch((err) => {
      setSetupArtStatus?.(err?.message || String(err), { bad: true });
    });
    return;
  }
  if (event.target.closest("[data-probe-iib]")) {
    event.preventDefault();
    const status = document.querySelector("#iibProbeStatus");
    if (status) {
      status.hidden = false;
      status.textContent = "Probing IIB…";
      status.classList.remove("bad", "good");
    }
    fetchImageBrowserState({ launch: false })
      .then((data) => {
        const iib = data.iib || {};
        if (status) {
          status.textContent = [
            iib.installed_on_disk ? "On disk" : "Not on disk",
            iib.online ? "online" : "offline",
            iib.message || "",
          ]
            .filter(Boolean)
            .join(" · ");
          status.classList.toggle("good", !!iib.online);
          status.classList.toggle("bad", !iib.online);
        }
      })
      .catch((err) => {
        if (status) {
          status.textContent = err?.message || String(err);
          status.classList.add("bad");
        }
      });
    return;
  }
  const iibView = event.target.closest("[data-iib-view]");
  if (iibView) {
    event.preventDefault();
    imageBrowserState.view = iibView.getAttribute("data-iib-view") || "auto";
    paintImageBrowserPanel();
    return;
  }
  if (event.target.closest("[data-iib-refresh]")) {
    event.preventDefault();
    const statusEls = document.querySelectorAll("#imageBrowserStatus, #setupImageBrowserStatus, .imageBrowserStatus");
    statusEls.forEach((status) => {
      status.textContent = "Refreshing…";
      status.classList.remove("bad", "good");
    });
    fetchImageBrowserState({ launch: false })
      .then(() => paintImageBrowserPanel())
      .catch((err) => {
        statusEls.forEach((status) => {
          status.textContent = err?.message || String(err);
          status.classList.add("bad");
        });
      });
    return;
  }
  if (event.target.closest("[data-iib-open-tab]")) {
    event.preventDefault();
    const url = imageBrowserState.iib?.open_url || imageBrowserState.iib?.embed_url;
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      fetchImageBrowserState({ launch: false }).then((data) => {
        const u = data.iib?.open_url || data.iib?.embed_url;
        if (u) window.open(u, "_blank", "noopener,noreferrer");
        else {
          const st = document.querySelector("#imageBrowserStatus");
          if (st) st.textContent = data.iib?.message || "IIB URL unavailable";
        }
      });
    }
    return;
  }
  const portraitUse = event.target.closest("[data-portrait-use]");
  if (portraitUse) {
    event.preventDefault();
    const slot = portraitUse.getAttribute("data-portrait-use") || "face";
    const id =
      portraitUse.getAttribute("data-portrait-id") ||
      portraitUse.closest("[data-portrait-id]")?.getAttribute("data-portrait-id") ||
      "";
    if (id) {
      applyNativePortraitToSlot(id, slot).catch((err) => {
        setSetupArtStatus?.(err?.message || String(err), { bad: true });
      });
    }
    return;
  }
  const portraitDelete = event.target.closest("[data-portrait-delete]");
  if (portraitDelete) {
    event.preventDefault();
    event.stopPropagation();
    const id =
      portraitDelete.getAttribute("data-portrait-delete") ||
      portraitDelete.closest("[data-portrait-id]")?.getAttribute("data-portrait-id") ||
      "";
    if (id) {
      deleteNativePortrait(id).catch((err) => {
        window.alert(err?.message || String(err));
      });
    }
    return;
  }
  const portraitFilter = event.target.closest("[data-portrait-filter]");
  if (portraitFilter) {
    event.preventDefault();
    const kind = portraitFilter.getAttribute("data-portrait-filter") || "all";
    const items = imageBrowserState.portraits?.items || [];
    const gridRoot = portraitFilter.closest(".nativePortraitHost");
    if (gridRoot) {
      const title = gridRoot.querySelector(".setupNativeStripTitle");
      const titleHtml = title ? title.outerHTML : "";
      const note = gridRoot.querySelector(":scope > .empty");
      const noteHtml = note ? note.outerHTML : "";
      gridRoot.innerHTML = titleHtml + noteHtml + renderNativePortraitGridHtml(items, kind);
    } else {
      document.querySelectorAll(".nativePortraitHost").forEach((host) => {
        const t = host.querySelector(".setupNativeStripTitle");
        const titleHtml = t ? t.outerHTML : "";
        const note = host.querySelector(":scope > .empty");
        const noteHtml = note ? note.outerHTML : "";
        host.innerHTML = titleHtml + noteHtml + renderNativePortraitGridHtml(items, kind);
      });
    }
    return;
  }
  if (event.target.closest("#studioSavePrimary")) {
    event.preventDefault();
    const primary = String(document.querySelector("#studioPrimaryPrompt")?.value || "").trim();
    const primaryNeg = String(document.querySelector("#studioPrimaryNegative")?.value || "").trim();
    const autoNpc = !!document.querySelector("#studioAutoNpc")?.checked;
    const status = document.querySelector("#studioStatus");
    fetch("/api/image-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...(imageConfig || {}),
        primary_prompt: primary,
        primary_negative: primaryNeg,
        auto_generate_npc_portraits: autoNpc,
      }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        imageConfig = await r.json();
        if (status) status.textContent = "Primary prompts + NPC auto-gen saved.";
        queueAutoNpcPortraits();
      })
      .catch((err) => {
        if (status) status.textContent = err.message || String(err);
      });
    return;
  }
  if (event.target.closest("#studioRefreshCatalog")) {
    event.preventDefault();
    refreshSetupArtCatalog().then(() => {
      const status = document.querySelector("#studioStatus");
      if (status) status.textContent = `Catalog: ${(setupArtLoraCatalog || []).length} LoRA(s).`;
    });
    return;
  }
  const candUse = event.target.closest("[data-cand-use]");
  if (candUse) {
    event.preventDefault();
    const card = candUse.closest("[data-cand-id]");
    const id = card?.getAttribute("data-cand-id");
    const asKind = candUse.getAttribute("data-cand-use");
    if (id && asKind) useStudioCandidate(id, asKind);
    return;
  }
});

document.addEventListener("input", (event) => {
  if (event.target?.id === "setupArtLoraFilter") {
    renderSetupLoraList(event.target.value || "");
  }
  if (
    event.target?.matches?.("#setupArtLoraList input[data-lora-name], #setupArtLoraList input[data-lora-weight]")
  ) {
    updateSetupLoraSummary();
  }
  const eng = event.target?.getAttribute?.("data-engine-prompt");
  if (eng) {
    const map = {
      face: "face",
      fullbody: "fullbody",
      body: "fullbody",
      face_negative: "face_negative",
      fullbody_negative: "fullbody_negative",
      negative: "face_negative",
    };
    markEnginePromptDirty(map[eng] || eng);
  }
});

document.addEventListener("change", (event) => {
  if (
    event.target?.matches?.("#setupArtLoraList input[data-lora-name], #setupArtLoraList input[data-lora-weight]")
  ) {
    updateSetupLoraSummary();
  }
});

/**
 * Ctrl+ArrowUp / Ctrl+ArrowDown on a comma-segment in an engine prompt:
 * standing → (standing:1.1) → (standing:1.2) …
 * long silver hair → (long silver hair:1.1) …
 * Steps of ±0.1. Weight 1.0 unwraps parentheses. Skips <lora:…> tags.
 */
function adjustPromptWeightAtCursor(textarea, delta) {
  if (!textarea || typeof textarea.value !== "string") return false;
  const value = textarea.value;
  let start = textarea.selectionStart ?? 0;
  let end = textarea.selectionEnd ?? start;
  // Expand to the nearest comma-separated segment (supports multi-word tags).
  if (start === end) {
    while (start > 0 && value[start - 1] !== ",") start -= 1;
    while (end < value.length && value[end] !== ",") end += 1;
  }
  while (start < end && /\s/.test(value[start])) start += 1;
  while (end > start && /\s/.test(value[end - 1])) end -= 1;
  if (start >= end) return false;
  const token = value.slice(start, end);
  // Do not reweight LoRA syntax
  if (/^<lora:/i.test(token) || /^</.test(token)) return false;
  const m = token.match(/^\((.+):([+-]?\d+(?:\.\d+)?)\)$/);
  let word;
  let weight;
  if (m) {
    word = m[1].trim();
    weight = parseFloat(m[2]);
  } else if (/^[\w][\w\s'.+\-]*$/.test(token) || /^[\w.-]+$/.test(token)) {
    word = token.trim();
    weight = 1.0;
  } else {
    return false;
  }
  if (!word) return false;
  weight = Math.round((weight + delta) * 10) / 10;
  weight = Math.max(0.1, Math.min(2.0, weight));
  // Back to bare word at ~1.0 so prompts stay clean
  const next = Math.abs(weight - 1.0) < 0.05 ? word : `(${word}:${weight.toFixed(1)})`;
  textarea.value = value.slice(0, start) + next + value.slice(end);
  const caret = start + next.length;
  textarea.setSelectionRange(start, caret);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

document.addEventListener("keydown", (event) => {
  const ta = event.target;
  if (!(ta instanceof HTMLTextAreaElement)) return;
  if (!ta.classList.contains("enginePromptField") && !ta.getAttribute("data-engine-prompt")) return;
  if (!event.ctrlKey || event.altKey || event.metaKey) return;
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  event.preventDefault();
  adjustPromptWeightAtCursor(ta, event.key === "ArrowUp" ? 0.1 : -0.1);
});

const ART_AUTO_UPDATE_KEY = "morkyn-art-auto-update-prompts";

function artAutoUpdateEnabled() {
  return !!document.querySelector("#setupArtAutoUpdate")?.checked;
}

function initArtAutoUpdateToggle() {
  const el = document.querySelector("#setupArtAutoUpdate");
  if (!el || el.dataset.bound === "1") return;
  el.dataset.bound = "1";
  try {
    el.checked = localStorage.getItem(ART_AUTO_UPDATE_KEY) === "1";
  } catch (_) {
    el.checked = false;
  }
  el.addEventListener("change", () => {
    try {
      localStorage.setItem(ART_AUTO_UPDATE_KEY, el.checked ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    if (el.checked) {
      // One refresh when turning on (respects dirty fields).
      rebuildEnginePrompts({ force: false, silent: false }).catch(() => {});
    }
  });
}

// Optional live rebuild when Auto update is on; otherwise only Randomize / Rebuild button.
let _engineRebuildTimer = null;
function scheduleEnginePromptRebuild() {
  if (!artAutoUpdateEnabled()) return;
  if (_engineRebuildTimer) window.clearTimeout(_engineRebuildTimer);
  _engineRebuildTimer = window.setTimeout(() => {
    rebuildEnginePrompts({ force: false, silent: true }).catch(() => {});
  }, 350);
}

document.addEventListener("input", (event) => {
  const form = event.target?.closest?.("#setupForm");
  if (!form) return;
  const name = event.target?.name || "";
  if (
    /^(player_name|player_public_name|player_title|player_age|player_sex|character_backstory|world_style|world_style_custom|start_location|setup_art_extra)/.test(
      name,
    ) ||
    event.target?.matches?.('input[name="world_style"]') ||
    event.target?.id === "setupArtExtra"
  ) {
    syncPortraitControls();
    scheduleEnginePromptRebuild();
  }
});
document.addEventListener("change", (event) => {
  const form = event.target?.closest?.("#setupForm");
  if (!form) return;
  const name = event.target?.name || "";
  if (
    /^(player_name|player_public_name|player_title|player_age|player_sex|character_backstory|world_style|world_style_custom)/.test(
      name,
    ) ||
    event.target?.matches?.('input[name="world_style"]') ||
    event.target?.closest?.("#setupArtLoraList")
  ) {
    syncPortraitControls();
    scheduleEnginePromptRebuild();
  }
});

indexContent.addEventListener("dragstart", (event) => {
  const card = event.target.closest(".entityCard");
  if (!card) return;
  event.dataTransfer.setData("text/plain", refToken(card.dataset.type, card.dataset.code));
});

turnInput.addEventListener("dragover", (event) => event.preventDefault());
turnInput.addEventListener("drop", (event) => {
  event.preventDefault();
  const token = event.dataTransfer.getData("text/plain");
  if (!token) return;
  const start = turnInput.selectionStart ?? turnInput.value.length;
  turnInput.value = `${turnInput.value.slice(0, start)} ${token} ${turnInput.value.slice(start)}`.replace(/\s+/g, " ").trimStart();
  turnInput.focus();
});

function hideScriptGate() {
  if (typeof window.__MORKYN_HIDE_GATE__ === "function") {
    window.__MORKYN_HIDE_GATE__();
  } else {
    window.__MORKYN_BOOTED__ = true;
    document.querySelector("#scriptGate")?.classList.add("hiddenGate");
    document.querySelector("main.app")?.classList.remove("jsPending");
    document.querySelector("main.app")?.classList.add("jsReady");
  }
}

/** UI theme: dusk | ember | tide | bloom | ash */
const THEME_KEY = "morkyn-ui-theme";
const THEME_DEFAULT = "dusk";

function applyUiTheme(theme) {
  const allowed = new Set(["dusk", "ember", "tide", "bloom", "ash"]);
  const next = allowed.has(theme) ? theme : THEME_DEFAULT;
  if (next === "dusk") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (_) {
    /* ignore */
  }
  const sel = document.querySelector("#themeSelect");
  if (sel && sel.value !== next) sel.value = next;
}

function initUiTheme() {
  let saved = THEME_DEFAULT;
  try {
    saved = localStorage.getItem(THEME_KEY) || THEME_DEFAULT;
  } catch (_) {
    saved = THEME_DEFAULT;
  }
  applyUiTheme(saved);
  const sel = document.querySelector("#themeSelect");
  if (sel) {
    sel.value = saved;
    sel.addEventListener("change", () => applyUiTheme(sel.value));
  }
}

function openLegalModal(title, subtitle, html) {
  if (!legalModal || !legalModalContent) return;
  if (legalModalTitle) legalModalTitle.textContent = title;
  if (legalModalSubtitle) legalModalSubtitle.textContent = subtitle || "";
  legalModalContent.innerHTML = html;
  legalModal.classList.remove("hidden");
}

function closeLegal() {
  legalModal?.classList.add("hidden");
}

async function showUpdatesModal() {
  openLegalModal("Updates & rollback", "Only contacts GitHub when you ask.", `<p class="empty">Loading local version…</p>`);
  try {
    const statusRes = await fetch("/api/updates/status");
    const status = await statusRes.json();
    legalModalContent.innerHTML = renderUpdatesPanel(status, null);
    wireUpdatesPanel();
  } catch (error) {
    legalModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  }
}

function renderUpdatesPanel(status, check) {
  const s = status || {};
  const c = check || {};
  const events = Array.isArray(s.recent_events) ? s.recent_events : [];
  const lkg = s.last_known_good || null;
  return `
    <div class="updatesPanel">
      <p class="empty">Mørkyn does not phone home for analytics. Update check/apply only talks to <strong>GitHub</strong> when you press a button below.</p>
      <div class="updatesGrid">
        <div><span class="muted">Version</span><strong>${escapeHtml(s.describe || "unknown")}</strong></div>
        <div><span class="muted">Branch</span><strong>${escapeHtml(s.branch || "—")}</strong></div>
        <div><span class="muted">HEAD</span><strong>${escapeHtml(s.head || "—")}</strong></div>
        <div><span class="muted">Dirty tree</span><strong>${s.dirty ? "yes (clean before update)" : "no"}</strong></div>
      </div>
      ${s.error && !s.ok ? `<p class="bad">${escapeHtml(s.error)}</p>` : ""}
      ${c.message ? `<p class="${c.update_available ? "good" : "empty"}">${escapeHtml(c.message)}</p>` : ""}
      ${c.latest_release?.tag ? `<p class="empty">Latest GitHub release: <strong>${escapeHtml(c.latest_release.tag)}</strong> ${c.latest_release.url ? `<a href="${escapeHtml(c.latest_release.url)}" target="_blank" rel="noopener">view</a>` : ""}</p>` : ""}
      ${lkg ? `<p class="empty">Last known good before update: <code>${escapeHtml(lkg.head || "")}</code> (${escapeHtml(lkg.describe || "")})</p>` : `<p class="empty">No rollback snapshot yet — created automatically when you apply an update.</p>`}
      <div class="modelButtonRow">
        <button type="button" class="secondaryButton" data-update-check>Check for updates</button>
        <button type="button" data-update-apply>Apply update</button>
        <button type="button" class="secondaryButton" data-update-rollback>Rollback</button>
      </div>
      <p class="empty">Apply uses fast-forward merge to <code>origin/main</code> (or master). Rollback restores the last-known-good commit from before an apply. Restart the launcher after either.</p>
      <div data-update-log class="updateLog"></div>
      ${events.length ? `<h3>Recent update events</h3><pre class="legalPre">${escapeHtml(events.map((e) => JSON.stringify(e)).join("\n"))}</pre>` : ""}
    </div>
  `;
}

function wireUpdatesPanel() {
  const root = legalModalContent;
  if (!root) return;
  const log = root.querySelector("[data-update-log]");
  const setLog = (html) => {
    if (log) log.innerHTML = html;
  };
  root.querySelector("[data-update-check]")?.addEventListener("click", async () => {
    setLog(`<p class="empty">Contacting GitHub / git remote…</p>`);
    try {
      const response = await fetch("/api/updates/check", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || "Check failed");
      const statusRes = await fetch("/api/updates/status");
      const status = await statusRes.json();
      legalModalContent.innerHTML = renderUpdatesPanel(status, data);
      wireUpdatesPanel();
    } catch (error) {
      setLog(`<p class="bad">${escapeHtml(error.message || String(error))}</p>`);
    }
  });
  root.querySelector("[data-update-apply]")?.addEventListener("click", async () => {
    if (!window.confirm("Apply update from the git remote? This only runs if your working tree is clean. Restart after.")) return;
    setLog(`<p class="empty">Applying update…</p>`);
    try {
      const response = await fetch("/api/updates/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, target: "" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || "Apply failed");
      setLog(`<p class="good">${escapeHtml(data.message || "Updated.")} HEAD ${escapeHtml(data.to || "")}</p>`);
    } catch (error) {
      setLog(`<p class="bad">${escapeHtml(error.message || String(error))}</p>`);
    }
  });
  root.querySelector("[data-update-rollback]")?.addEventListener("click", async () => {
    if (!window.confirm("Roll back to last known good (or fail if none)? Restart after.")) return;
    setLog(`<p class="empty">Rolling back…</p>`);
    try {
      const response = await fetch("/api/updates/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, target: "" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || "Rollback failed");
      setLog(`<p class="good">${escapeHtml(data.message || "Rolled back.")} HEAD ${escapeHtml(data.to || "")}</p>`);
    } catch (error) {
      setLog(`<p class="bad">${escapeHtml(error.message || String(error))}</p>`);
    }
  });
}

function bindUpdatesClick(el) {
  el?.addEventListener("click", () => {
    showUpdatesModal().catch((error) => {
      openLegalModal("Updates", "", `<p class="bad">${escapeHtml(error.message || String(error))}</p>`);
    });
  });
}
bindUpdatesClick(updatesButton);
bindUpdatesClick(document.querySelector("#playUpdatesButton"));
closeLegalModal?.addEventListener("click", closeLegal);
legalModal?.addEventListener("click", (event) => {
  if (event.target === legalModal) closeLegal();
});

initUiTheme();
hydrateNpcPortraitCache();
bindArtDropZones();
initArtAutoUpdateToggle();
initSetupArtCollapse();
setArtPromptTab("face");
try {
  const savedArtBackend = localStorage.getItem("morkyn-setup-art-backend");
  if (savedArtBackend === "comfyui" || savedArtBackend === "forge") {
    setSetupArtBackendTab(savedArtBackend);
  }
} catch (_) {
  /* ignore */
}
loadImageConfig()
  .then(() => {
    syncPortraitControls();
    // Prompts: only fill on Randomize finish / Rebuild (or if Auto update is on after identity edits).
    refreshSetupArtCatalog().catch(() => {});
    queueAutoNpcPortraits();
    startForgeImageGatePoll();
    return probeImageBackendStatus({ silent: true });
  })
  .catch(() => {
    imageConfig = { provider: "off", enabled: false };
    forgeImageStatus = { ok: false, provider: "off", message: "Image backend off" };
    syncPortraitControls();
    syncForgeImageGateUi();
    startForgeImageGatePoll();
  });
// --- World map presets + tile image archive ---------------------------------

let worldPresets = [];
let tileStates = [];
let activeMap = null;
let tileLibSelection = new Set();
/** Preferred sprite size for map cells: 16 or 32 (pixel art). Declared early for init. */
let mapTilePx = Number(localStorage.getItem("morkyn-map-tile-px") || 32) === 16 ? 16 : 32;
let mapAvatarUrl = localStorage.getItem("morkyn-map-avatar") || "";
const _pixelTileCache = new Map();
const _imageCache = new Map();

initWorldMapUi().catch(() => {});
// Defer avatar tool bind until DOM handlers exist further down (function is hoisted).
// mapTilePx/mapAvatarUrl must already be initialized above.
bindMapAvatarTools();
hideScriptGate();

async function initWorldMapUi() {
  const presetSel = document.querySelector("#mapPresetSelect");
  const stateSel = document.querySelector("#tileLibState");
  const asciiEl = document.querySelector("#mapAscii");
  try {
    const [pRes, sRes] = await Promise.all([
      fetch("/api/tiles/presets"),
      fetch("/api/tiles/states"),
    ]);
    if (pRes.ok) {
      const data = await pRes.json();
      worldPresets = data.presets || [];
    } else if (asciiEl) {
      asciiEl.textContent = `Presets failed to load (HTTP ${pRes.status}). Restart the app so /api/tiles/* routes are live.`;
    }
    if (sRes.ok) {
      const data = await sRes.json();
      tileStates = data.states || [];
    }
  } catch (error) {
    worldPresets = [];
    tileStates = [];
    if (asciiEl) asciiEl.textContent = `Map API error: ${error.message || error}`;
  }
  if (presetSel) {
    if (!worldPresets.length) {
      presetSel.innerHTML = `<option value="">No presets (restart server)</option>`;
    } else {
      presetSel.innerHTML = worldPresets
        .map(
          (p) =>
            `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)} · ${escapeHtml(p.age)} / ${escapeHtml(p.environment)}</option>`
        )
        .join("");
      if (!presetSel.value && worldPresets[0]) presetSel.value = worldPresets[0].id;
    }
  }
  if (stateSel) {
    stateSel.innerHTML =
      `<option value="">All states</option>` +
      tileStates
        .map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.label)} (${escapeHtml(s.id)})</option>`)
        .join("");
  }
  // Restore last map; if none, auto-generate so the board is visible.
  try {
    const res = await fetch("/api/tiles/map");
    if (res.ok) {
      const data = await res.json();
      if (data && !data.empty && data.id) {
        activeMap = data;
        renderMapPreview(activeMap);
        return;
      }
    }
  } catch (_) {
    /* none yet */
  }
  if (worldPresets.length) {
    try {
      await generateWorldMap();
    } catch (error) {
      if (asciiEl) asciiEl.textContent = `Auto-generate failed: ${error.message || error}. Press Generate.`;
    }
  }
}

const MAP_STATE_COLORS = {
  water: "#2a5f8f",
  plains: "#6b8f4e",
  forest: "#2f5d34",
  desert: "#c2a15a",
  mountain: "#7a7a86",
  hill: "#8a9a5b",
  cliff: "#5c5c66",
  city: "#c9a227",
  town: "#d4b56a",
  village: "#b8956a",
  road: "#9a8060",
  ruins: "#8b6f6f",
  monolith: "#b07cff",
  void: "#0b0d12",
  asteroid: "#6e6a62",
  station: "#6ec0ff",
  ash: "#6a6660",
  lava: "#c23b22",
  ice: "#a8d4e6",
  swamp: "#3d5c3a",
  beach: "#d2c08a",
  dungeon: "#3a3040",
  cavern: "#4a3f4a",
};

function paintMapCanvas(mapData, canvas) {
  if (!canvas || !mapData) return;
  const width = Number(mapData.width || 0);
  const height = Number(mapData.height || 0);
  let tiles = Array.isArray(mapData.tiles) ? mapData.tiles : [];
  if ((!tiles.length || !width || !height) && Array.isArray(mapData.grid)) {
    tiles = mapData.grid.flat();
  }
  if (!width || !height || !tiles.length) {
    canvas.width = 8;
    canvas.height = 8;
    return;
  }
  const cell = Math.max(4, Math.min(14, Math.floor(520 / Math.max(width, height))));
  canvas.width = width * cell;
  canvas.height = height * cell;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#12151c";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const byPos = new Map();
  tiles.forEach((t) => {
    if (t && t.x != null && t.y != null) byPos.set(`${t.x},${t.y}`, t);
  });
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const t = byPos.get(`${x},${y}`) || (Array.isArray(mapData.grid) ? mapData.grid[y]?.[x] : null) || {};
      const state = String(t.state || "?");
      ctx.fillStyle = MAP_STATE_COLORS[state] || "#3a4150";
      ctx.fillRect(x * cell, y * cell, cell, cell);
    }
  }
  const px = Number(mapData.player?.x);
  const py = Number(mapData.player?.y);
  if (Number.isFinite(px) && Number.isFinite(py)) {
    ctx.fillStyle = "#ff4d6d";
    ctx.fillRect(px * cell, py * cell, cell, cell);
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1;
    ctx.strokeRect(px * cell + 0.5, py * cell + 0.5, cell - 1, cell - 1);
  }
}

function renderMapPreview(mapData) {
  const asciiEl = document.querySelector("#mapAscii");
  const metaEl = document.querySelector("#mapMeta");
  const badge = document.querySelector("#mapFrame .visionBadge");
  const canvas = document.querySelector("#mapCanvas");
  const playCanvas = document.querySelector("#playMapCanvas");
  const playAscii = document.querySelector("#playMapAscii");
  if (!mapData) return;
  activeMap = mapData;
  const ascii = mapData.ascii || "(no preview — press Generate)";
  if (asciiEl) {
    asciiEl.textContent = ascii;
    asciiEl.classList.toggle("mapAsciiEmpty", !mapData.ascii || mapData.empty);
  }
  if (playAscii) playAscii.textContent = ascii;
  paintMapCanvas(mapData, canvas);
  paintMapCanvas(mapData, playCanvas);
  if (badge) {
    badge.textContent = `${mapData.preset_id || "map"} · seed ${mapData.seed}`;
  }
  if (metaEl) {
    const stats = mapData.stats || {};
    const counts = stats.state_counts || {};
    const top = Object.entries(counts)
      .slice(0, 10)
      .map(([k, v]) => `<span>${escapeHtml(k)} ${v}</span>`)
      .join("");
    const missing = (stats.missing_art_states || []).slice(0, 8).join(", ");
    metaEl.innerHTML = `
      <p><strong>${escapeHtml(mapData.age || "")}</strong> · ${escapeHtml(mapData.environment || "")}
      · ${mapData.width}×${mapData.height}
      · you @ (${mapData.player?.x}, ${mapData.player?.y})
      · art ${stats.image_assigned || 0}/${stats.cells || 0}</p>
      <div class="mapStats">${top}</div>
      <p class="mapLegend">Red cell = you · color blocks = terrain states · ASCII backup below.</p>
      ${missing ? `<p class="empty">No art yet for: ${escapeHtml(missing)}. Use Tile library → Generate.</p>` : ""}
    `;
  }
  const playMeta = document.querySelector("#playMapMeta");
  if (playMeta) {
    playMeta.textContent = `${mapData.preset_id || "map"} ${mapData.width}×${mapData.height} · @(${mapData.player?.x},${mapData.player?.y})`;
  }
}

async function generateWorldMap() {
  const preset = document.querySelector("#mapPresetSelect")?.value || "forest_march";
  const seedRaw = document.querySelector("#mapSeedInput")?.value;
  const seed = seedRaw === "" || seedRaw == null ? null : Number(seedRaw);
  const asciiEl = document.querySelector("#mapAscii");
  if (asciiEl) asciiEl.textContent = "Generating…";
  const response = await fetch("/api/tiles/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      preset_id: preset,
      seed: Number.isFinite(seed) ? seed : null,
      assign_images: true,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || "Map generation failed");
  renderMapPreview(data);
  return data;
}

function openTileLibrary() {
  document.querySelector("#tileLibraryPanel")?.classList.remove("hidden");
  searchTileLibrary().catch(() => {});
}

function closeTileLibrary() {
  document.querySelector("#tileLibraryPanel")?.classList.add("hidden");
}

async function searchTileLibrary() {
  const query = document.querySelector("#tileLibQuery")?.value || "";
  const state_id = document.querySelector("#tileLibState")?.value || "";
  const include_disabled = !!document.querySelector("#tileLibShowDisabled")?.checked;
  const run_id = activeMap?.run_id || activeMap?.id || "";
  const response = await fetch("/api/tiles/images/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, state_id, include_disabled, run_id, limit: 120 }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Search failed");
  renderTileLibrary(data.images || []);
}

function renderTileLibrary(images) {
  const grid = document.querySelector("#tileLibraryGrid");
  if (!grid) return;
  tileLibSelection = new Set();
  if (!images.length) {
    grid.innerHTML = `<p class="empty">No images yet. Generate art for a state or add your own later.</p>`;
    return;
  }
  grid.innerHTML = images
    .map((img) => {
      const disabled = !!img.disabled_forever;
      const src = img.data_url || "";
      const thumb = src
        ? `<img class="tileLibThumb" src="${src}" alt="" />`
        : `<div class="tileLibThumb placeholder">${escapeHtml(img.state_id || "?")}</div>`;
      return `
        <article class="tileLibCard ${disabled ? "disabled" : ""}" data-image-id="${img.id}">
          <label><input type="checkbox" data-tile-select value="${img.id}" /> ${escapeHtml(img.state_id)}</label>
          ${thumb}
          <div>${escapeHtml(img.source || "")} · ${escapeHtml(img.quality || "")}</div>
        </article>
      `;
    })
    .join("");
  grid.querySelectorAll("[data-tile-select]").forEach((box) => {
    box.addEventListener("change", () => {
      const id = Number(box.value);
      if (box.checked) tileLibSelection.add(id);
      else tileLibSelection.delete(id);
    });
  });
}

function selectedTileImageIds() {
  return [...tileLibSelection];
}

async function bulkTileImages(action) {
  const ids = selectedTileImageIds();
  if (!ids.length) {
    window.alert("Select one or more tile images first.");
    return;
  }
  const run_id = activeMap?.run_id || activeMap?.id || "";
  let url = "";
  let body = { image_ids: ids, run_id, disabled: true };
  if (action === "disable-forever") url = "/api/tiles/images/disable-forever";
  else if (action === "enable") {
    url = "/api/tiles/images/disable-forever";
    body.disabled = false;
  } else if (action === "disable-run") {
    if (!run_id) {
      window.alert("Generate a map first so we have a run id.");
      return;
    }
    url = "/api/tiles/images/disable-run";
  } else if (action === "delete") {
    if (!window.confirm(`Delete ${ids.length} image(s) permanently?`)) return;
    url = "/api/tiles/images/delete";
  } else return;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Bulk action failed");
  }
  await searchTileLibrary();
}

async function generateTileArtForSelectedState() {
  const state_id = document.querySelector("#tileLibState")?.value || "";
  if (!state_id) {
    window.alert("Pick a tile state in the library filter first.");
    return;
  }
  const preset_id = document.querySelector("#mapPresetSelect")?.value || "";
  const response = await fetch("/api/tiles/images/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      state_id,
      preset_id,
      quality: "8bit",
      width: 64,
      height: 64,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || "Tile generate failed");
  await searchTileLibrary();
  return data;
}

document.querySelector("#mapRegenBtn")?.addEventListener("click", () => {
  generateWorldMap().catch((error) => {
    const asciiEl = document.querySelector("#mapAscii");
    if (asciiEl) asciiEl.textContent = `Error: ${error.message || error}`;
  });
});
document.querySelector("#mapLibraryBtn")?.addEventListener("click", () => openTileLibrary());
document.querySelector("#tileLibraryClose")?.addEventListener("click", () => closeTileLibrary());
document.querySelector("#tileLibSearch")?.addEventListener("click", () => {
  searchTileLibrary().catch((e) => window.alert(e.message || e));
});
document.querySelector("#tileLibGenerate")?.addEventListener("click", () => {
  generateTileArtForSelectedState().catch((e) => window.alert(e.message || e));
});
document.querySelectorAll("[data-tile-bulk]").forEach((btn) => {
  btn.addEventListener("click", () => {
    bulkTileImages(btn.getAttribute("data-tile-bulk")).catch((e) => window.alert(e.message || e));
  });
});
// --- Skill check catalog (setup tab 5) ------------------------------------
let skillCatalogCache = { categories: [], skills: [], filter: "all" };

function renderCheckCategoryFilters() {
  const filters = document.querySelector("#checkCategoryFilters");
  if (!filters) return;
  const cats = [{ id: "all", label: "All" }, ...(skillCatalogCache.categories || [])];
  filters.innerHTML = cats
    .map(
      (c) =>
        `<button type="button" class="secondaryButton compactButton ${skillCatalogCache.filter === c.id ? "activeFilter" : ""}" data-check-cat="${escapeHtml(c.id)}">${escapeHtml(c.label || c.id)}</button>`
    )
    .join("");
  filters.querySelectorAll("[data-check-cat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      skillCatalogCache.filter = btn.getAttribute("data-check-cat") || "all";
      renderCheckCategoryFilters();
      renderSkillCatalog();
    });
  });
}

function renderSkillCatalog() {
  const grid = document.querySelector("#skillCatalogGrid");
  if (!grid) return;
  const filter = skillCatalogCache.filter || "all";
  const skills = (skillCatalogCache.skills || []).filter(
    (s) => filter === "all" || s.category === filter
  );
  if (!skills.length) {
    grid.innerHTML = `<p class="empty">No skills in this category.</p>`;
    return;
  }
  grid.innerHTML = skills
    .map((s) => {
      const on = s.enabled !== false;
      return `
      <article class="skillCatalogCard ${on ? "" : "disabledSkill"}" data-skill-code="${escapeHtml(s.code)}">
        <header>
          <strong>${escapeHtml(s.name)}</strong>
          <span class="skillCatPill">${escapeHtml(s.category || "general")}</span>
        </header>
        <p class="skillMeta">${escapeHtml(s.attribute || "?")} · DC ${escapeHtml(s.base_dc ?? 12)} · ${escapeHtml(s.source || "")}${s.times_seen ? ` · seen ${s.times_seen}` : ""}</p>
        <p class="skillDesc">${escapeHtml(s.description || "—")}</p>
        <label class="settingLock"><input type="checkbox" data-skill-enable="${escapeHtml(s.code)}" ${on ? "checked" : ""} /> Enabled for play</label>
      </article>`;
    })
    .join("");
  grid.querySelectorAll("[data-skill-enable]").forEach((input) => {
    input.addEventListener("change", async () => {
      const code = input.getAttribute("data-skill-enable");
      try {
        const res = await fetch("/api/skill-checks/enable", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, enabled: Boolean(input.checked) }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Enable failed");
        const skill = skillCatalogCache.skills.find((s) => s.code === code);
        if (skill) skill.enabled = Boolean(input.checked);
        renderSkillCatalog();
      } catch (error) {
        window.alert(error.message || String(error));
        input.checked = !input.checked;
      }
    });
  });
}

async function loadSkillCatalog() {
  const grid = document.querySelector("#skillCatalogGrid");
  try {
    const res = await fetch("/api/skill-checks/catalog", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Catalog failed");
    skillCatalogCache.categories = data.categories || [];
    skillCatalogCache.skills = data.skills || [];
    renderCheckCategoryFilters();
    renderSkillCatalog();
  } catch (error) {
    if (grid) grid.innerHTML = `<p class="empty">Could not load skills: ${escapeHtml(error.message || String(error))}</p>`;
  }
}

document.querySelector("#skillCatalogRefresh")?.addEventListener("click", () => loadSkillCatalog());
document.querySelector("#skillCatalogAdd")?.addEventListener("click", () => {
  document.querySelector("#skillAddRow")?.classList.toggle("hidden");
});
document.querySelector("#newSkillSave")?.addEventListener("click", async () => {
  const name = document.querySelector("#newSkillName")?.value?.trim() || "";
  if (!name) {
    window.alert("Name is required");
    return;
  }
  try {
    const res = await fetch("/api/skill-checks/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        category: document.querySelector("#newSkillCategory")?.value || "general",
        attribute: document.querySelector("#newSkillAttribute")?.value || "intelligence",
        description: document.querySelector("#newSkillDesc")?.value || "",
        source: "user",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Register failed");
    const similar = (data.similar || []).map((s) => s.name).filter(Boolean).slice(0, 3);
    if (similar.length) {
      window.alert(`Saved. Adjusted against similar: ${similar.join(", ")}`);
    }
    if (document.querySelector("#newSkillName")) document.querySelector("#newSkillName").value = "";
    if (document.querySelector("#newSkillDesc")) document.querySelector("#newSkillDesc").value = "";
    document.querySelector("#skillAddRow")?.classList.add("hidden");
    await loadSkillCatalog();
  } catch (error) {
    window.alert(error.message || String(error));
  }
});

// --- Local map, full map overlay, NPC stage -------------------------------
let localMapView = null;
let fullMapView = null;
let travelReady = true;
let focusedNpcCode = "";
const npcPortraitCache = {};

function updateTravelStatus(ready) {
  travelReady = ready !== false;
  const line = document.querySelector("#travelStatusLine");
  const banner = document.querySelector("#mapTravelBanner");
  const walkBtn = document.querySelector("#settlementWalkBtn");
  const text = travelReady
    ? "Travel open — you can pick a destination on the Map."
    : "Travel locked — finish the current scene/event first.";
  if (line) {
    line.textContent = text;
    line.classList.toggle("locked", !travelReady);
  }
  if (banner) {
    banner.textContent = text;
    banner.classList.toggle("locked", !travelReady);
  }
  if (walkBtn) walkBtn.disabled = !travelReady;
}

function loadImageEl(src) {
  if (!src) return Promise.resolve(null);
  if (_imageCache.has(src)) return Promise.resolve(_imageCache.get(src));
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      _imageCache.set(src, img);
      resolve(img);
    };
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** Procedural 16×16 / 32×32 pixel terrain (fallback when archive art missing). */
function getPixelTileSprite(state, size = 16) {
  const key = `${state}|${size}`;
  if (_pixelTileCache.has(key)) return _pixelTileCache.get(key);
  const s = Math.max(16, Math.min(32, size));
  const c = document.createElement("canvas");
  c.width = s;
  c.height = s;
  const ctx = c.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const base = MAP_STATE_COLORS[state] || "#3a4150";
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, s, s);
  // Dither / detail in true pixel steps
  const step = s === 16 ? 1 : 2;
  const darken = (hex, a) => {
    ctx.fillStyle = hex;
    ctx.globalAlpha = a;
  };
  // simple pattern families
  if (state === "water" || state === "waterfall") {
    darken("#1a3a5c", 1);
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#3d7ab0";
    for (let y = 0; y < s; y += step * 2) {
      for (let x = (y / step) % 2 === 0 ? 0 : step; x < s; x += step * 2) {
        ctx.fillRect(x, y, step, step);
      }
    }
    ctx.fillStyle = "#8fd0ff";
    ctx.globalAlpha = 0.5;
    ctx.fillRect(step * 2, step * 3, step, step);
    ctx.globalAlpha = 1;
  } else if (state === "forest" || state === "swamp") {
    ctx.fillStyle = "#1e4a28";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#2f7a3a";
    for (let i = 0; i < 8; i += 1) {
      const x = ((i * 5) % (s - step * 2)) + step;
      const y = ((i * 7) % (s - step * 2)) + step;
      ctx.fillRect(x, y, step * 2, step * 2);
    }
    ctx.fillStyle = "#0e2014";
    ctx.fillRect(s / 2 - step, s - step * 3, step * 2, step * 3);
  } else if (state === "mountain" || state === "cliff" || state === "hill" || state === "volcano") {
    ctx.fillStyle = "#4a4a55";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#8a8a96";
    ctx.beginPath();
    ctx.moveTo(s / 2, step);
    ctx.lineTo(s - step, s - step);
    ctx.lineTo(step, s - step);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#dfe6f0";
    ctx.fillRect(s / 2 - step, step * 2, step * 2, step);
  } else if (state === "city" || state === "town" || state === "village" || state === "station" || state === "colony") {
    ctx.fillStyle = "#3a3428";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#c9a227";
    ctx.fillRect(step * 2, step * 4, s - step * 4, s - step * 5);
    ctx.fillStyle = "#6a5030";
    ctx.fillRect(step * 3, step * 2, s - step * 6, step * 3);
    ctx.fillStyle = "#ffef9a";
    ctx.fillRect(step * 4, step * 6, step, step);
    ctx.fillRect(s - step * 5, step * 6, step, step);
  } else if (state === "desert" || state === "beach" || state === "ash") {
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "rgba(255,255,255,0.15)";
    for (let y = step; y < s; y += step * 3) {
      ctx.fillRect(0, y, s, step);
    }
  } else if (state === "road" || state === "bridge") {
    ctx.fillStyle = "#5a6a3a";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#9a8060";
    ctx.fillRect(0, s / 2 - step * 2, s, step * 4);
    ctx.fillStyle = "#c4b08a";
    ctx.fillRect(0, s / 2 - step, s, step * 2);
  } else if (state === "void" || state === "nebula") {
    ctx.fillStyle = "#05060a";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "#fff";
    for (let i = 0; i < 6; i += 1) {
      ctx.globalAlpha = 0.4 + (i % 3) * 0.15;
      ctx.fillRect((i * 7) % s, (i * 11) % s, step, step);
    }
    ctx.globalAlpha = 1;
  } else {
    // plains / default dither
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    for (let y = 0; y < s; y += step * 2) {
      for (let x = (y / step) % 2 === 0 ? 0 : step; x < s; x += step * 2) {
        ctx.fillRect(x, y, step, step);
      }
    }
  }
  // pixel border
  ctx.globalAlpha = 0.35;
  ctx.strokeStyle = "#000";
  ctx.strokeRect(0.5, 0.5, s - 1, s - 1);
  ctx.globalAlpha = 1;
  _pixelTileCache.set(key, c);
  return c;
}

/**
 * Crop the upper-center of a portrait into a circular head token.
 * No baked-in border — map UI draws the ring when painting tokens.
 */
async function cropHeadDataUrl(src, outSize = 32) {
  const img = await loadImageEl(src);
  if (!img) return "";
  const size = Math.max(16, Math.min(128, Number(outSize) || 32));
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  const ctx = c.getContext("2d");
  if (!ctx) return "";
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, size, size);
  const iw = img.naturalWidth || img.width || 1;
  const ih = img.naturalHeight || img.height || 1;
  const side = Math.min(iw, ih);
  const sx = Math.max(0, (iw - side) / 2);
  const sy = Math.max(0, (ih - side) * 0.08);
  // Upper face crop (not full square gen with empty corners / frames)
  const sh = side * 0.55;
  const sw = side * 0.55;
  const sxx = sx + (side - sw) / 2;
  ctx.save();
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2);
  ctx.closePath();
  ctx.clip();
  ctx.drawImage(img, sxx, sy, sw, sh, 0, 0, size, size);
  ctx.restore();
  return c.toDataURL("image/png");
}

/** Draw a circular head token + coded map ring (border is UI, not in the PNG). */
function drawMapHeadToken(ctx, headImg, dx, dy, cell) {
  if (!ctx || !headImg) return;
  const pad = Math.max(1, Math.floor(cell * 0.12));
  const size = Math.max(2, cell - pad * 2);
  const x = dx + pad;
  const y = dy + pad;
  const cx = x + size / 2;
  const cy = y + size / 2;
  const r = size / 2;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.closePath();
  ctx.clip();
  ctx.drawImage(headImg, x, y, size, size);
  ctx.restore();
  // Outer dark + inner light ring so the token reads on any terrain
  const ringW = Math.max(1, Math.round(cell / 18));
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(1, r - ringW * 0.35), 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(0, 0, 0, 0.72)";
  ctx.lineWidth = ringW + 1;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(1, r - ringW * 0.35), 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
  ctx.lineWidth = ringW;
  ctx.stroke();
}

function updateMapAvatarPreview(url) {
  mapAvatarUrl = url || "";
  const img = document.querySelector("#mapAvatarPreview");
  const ph = document.querySelector("#mapAvatarPlaceholder");
  if (img && url) {
    img.src = url;
    img.classList.remove("hidden");
    ph?.classList.add("hidden");
  } else {
    img?.classList.add("hidden");
    ph?.classList.remove("hidden");
  }
}

async function paintTileGrid(canvas, tiles, options = {}) {
  if (!canvas || !tiles?.length) return;
  const fog = Boolean(options.fog);
  const tilePx = options.tilePx === 16 ? 16 : options.tilePx === 32 ? 32 : mapTilePx;
  // Display scale: each logical tile is tilePx art, optionally scaled for full map
  const scale = options.scale || (options.mode === "full" ? 1 : Math.max(1, Math.floor((options.cell || 32) / tilePx)));
  const cell = tilePx * scale;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  tiles.forEach((t) => {
    const x = Number(t.rel_x != null ? t.rel_x : t.x);
    const y = Number(t.rel_y != null ? t.rel_y : t.y);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  });
  if (!Number.isFinite(minX)) return;
  const w = maxX - minX + 1;
  const h = maxY - minY + 1;
  canvas.width = w * cell;
  canvas.height = h * cell;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#080b10";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Preload archive images + avatar
  const urls = [];
  tiles.forEach((t) => {
    if (t.image_data_url) urls.push(t.image_data_url);
    if (t.image_path && !String(t.image_path).startsWith("data:")) {
      /* path alone may not be browser-served */
    }
  });
  const avatarSrc = options.avatarUrl || mapAvatarUrl;
  if (avatarSrc) urls.push(avatarSrc);
  await Promise.all(urls.map((u) => loadImageEl(u)));

  for (const t of tiles) {
    const x = Number(t.rel_x != null ? t.rel_x : t.x) - minX;
    const y = Number(t.rel_y != null ? t.rel_y : t.y) - minY;
    const dx = x * cell;
    const dy = y * cell;
    const hidden = fog && t.fog && !t.is_player && !t.visited;
    if (hidden) {
      ctx.fillStyle = "#12151c";
      ctx.fillRect(dx, dy, cell, cell);
      // sparse noise
      ctx.fillStyle = "#1a1e28";
      ctx.fillRect(dx + 2, dy + 2, 2, 2);
      continue;
    }
    const state = String(t.state || "?");
    const archive = t.image_data_url ? _imageCache.get(t.image_data_url) : null;
    if (archive) {
      ctx.globalAlpha = fog && !t.visited ? 0.4 : 1;
      ctx.drawImage(archive, dx, dy, cell, cell);
      ctx.globalAlpha = 1;
    } else {
      const sprite = getPixelTileSprite(state, tilePx);
      ctx.globalAlpha = fog && !t.visited ? 0.4 : 1;
      ctx.drawImage(sprite, dx, dy, cell, cell);
      ctx.globalAlpha = 1;
    }
    if (t.is_settlement) {
      ctx.strokeStyle = "#ffd56a";
      ctx.lineWidth = Math.max(1, cell / 16);
      ctx.strokeRect(dx + 1, dy + 1, cell - 2, cell - 2);
    }
    if (t.is_player) {
      const head = avatarSrc ? _imageCache.get(avatarSrc) : null;
      if (head) {
        // Circle crop + coded ring (border is map chrome, not in the image)
        drawMapHeadToken(ctx, head, dx, dy, cell);
      } else {
        // fallback circular marker
        const pad = Math.floor(cell * 0.18);
        const size = cell - pad * 2;
        const cx = dx + pad + size / 2;
        const cy = dy + pad + size / 2;
        const r = size / 2;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = "#ff4d6d";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(cx, cy - r * 0.12, r * 0.38, 0, Math.PI * 2);
        ctx.fillStyle = "#ffd0d8";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(cx, cy, r - 0.5, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = Math.max(1, cell / 18);
        ctx.stroke();
      }
    }
  }
  canvas._mapMeta = { minX, minY, cell, mode: options.mode || "local", tilePx };
}

async function refreshLocalMap() {
  const canvas = document.querySelector("#playMapCanvas");
  const meta = document.querySelector("#playMapMeta");
  try {
    const res = await fetch("/api/tiles/map/local?radius=6", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok || data.empty) {
      if (meta) meta.textContent = "No map yet — generate on World setup.";
      return;
    }
    localMapView = data;
    if (data.map_avatar?.data_url) {
      mapAvatarUrl = data.map_avatar.data_url;
      localStorage.setItem("morkyn-map-avatar", mapAvatarUrl);
      updateMapAvatarPreview(mapAvatarUrl);
    } else if (data.map_avatar?.portrait_data_url && !mapAvatarUrl) {
      // soft hint only
      updateMapAvatarPreview("");
    }
    if (data.tile_px === 16 || data.tile_px === 32) {
      mapTilePx = data.tile_px;
      const sel = document.querySelector("#mapTilePxSelect");
      if (sel) sel.value = String(mapTilePx);
    }
    const cellDisplay = mapTilePx; // 1:1 pixel tiles on nearby map
    await paintTileGrid(canvas, data.tiles || [], {
      cell: cellDisplay,
      tilePx: mapTilePx,
      scale: 1,
      fog: false,
      mode: "local",
      avatarUrl: mapAvatarUrl,
    });
    if (meta) {
      meta.textContent = `@(${data.player?.x},${data.player?.y}) · ${mapTilePx}px tiles · visited ${data.visited_count || 0}`;
    }
  } catch (error) {
    if (meta) meta.textContent = `Map error: ${error.message || error}`;
  }
}

async function refreshFullMap() {
  const canvas = document.querySelector("#fullMapCanvas");
  try {
    const res = await fetch("/api/tiles/map/full", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok || data.empty) return;
    fullMapView = data;
    if (data.map_avatar?.data_url) {
      mapAvatarUrl = data.map_avatar.data_url;
      updateMapAvatarPreview(mapAvatarUrl);
    }
    await paintTileGrid(canvas, data.tiles || [], {
      tilePx: mapTilePx,
      scale: mapTilePx === 16 ? 1 : 1,
      cell: mapTilePx,
      fog: true,
      mode: "full",
      avatarUrl: mapAvatarUrl,
    });
    renderSettlementList(data.settlements || []);
  } catch (_) {
    /* ignore */
  }
}

async function saveMapAvatar(dataUrl, source = "upload") {
  const res = await fetch("/api/map-avatar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_url: dataUrl, tile_px: mapTilePx, from_portrait: source === "portrait_head" }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Save failed");
  mapAvatarUrl = dataUrl;
  localStorage.setItem("morkyn-map-avatar", dataUrl);
  updateMapAvatarPreview(dataUrl);
  await refreshLocalMap();
  if (!document.querySelector("#mapOverlay")?.classList.contains("hidden")) await refreshFullMap();
}

async function mapAvatarFromPortrait() {
  const portrait =
    state?.player_portrait?.data_url ||
    localStorage.getItem("morkyn-player-portrait") ||
    "";
  if (!portrait) {
    // try server
    const res = await fetch("/api/map-avatar");
    const info = await res.json().catch(() => ({}));
    if (info.portrait_data_url) {
      const head = await cropHeadDataUrl(info.portrait_data_url, mapTilePx);
      if (head) await saveMapAvatar(head, "portrait_head");
      return;
    }
    window.alert("Generate a player portrait first (Player tab → Regenerate), then use portrait head.");
    return;
  }
  const head = await cropHeadDataUrl(portrait, mapTilePx);
  if (!head) throw new Error("Could not crop head");
  await saveMapAvatar(head, "portrait_head");
}

function bindMapAvatarTools() {
  const tileSel = document.querySelector("#mapTilePxSelect");
  if (tileSel) {
    tileSel.value = String(mapTilePx);
    tileSel.addEventListener("change", async () => {
      mapTilePx = Number(tileSel.value) === 16 ? 16 : 32;
      localStorage.setItem("morkyn-map-tile-px", String(mapTilePx));
      // persist preference with current avatar if any
      if (mapAvatarUrl) {
        try {
          await fetch("/api/map-avatar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data_url: mapAvatarUrl, tile_px: mapTilePx }),
          });
        } catch (_) {
          /* ignore */
        }
      }
      await refreshLocalMap();
      if (!document.querySelector("#mapOverlay")?.classList.contains("hidden")) await refreshFullMap();
    });
  }
  document.querySelector("#mapAvatarFromPortrait")?.addEventListener("click", () => {
    mapAvatarFromPortrait().catch((e) => window.alert(e.message || e));
  });
  document.querySelector("#mapAvatarClear")?.addEventListener("click", async () => {
    try {
      await fetch("/api/map-avatar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear: true }),
      });
      mapAvatarUrl = "";
      localStorage.removeItem("morkyn-map-avatar");
      updateMapAvatarPreview("");
      await refreshLocalMap();
    } catch (e) {
      window.alert(e.message || e);
    }
  });
  document.querySelector("#mapAvatarUpload")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 900_000) {
      window.alert("Keep head images under ~900KB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        let dataUrl = String(reader.result || "");
        // Normalize to square head-ish crop
        dataUrl = (await cropHeadDataUrl(dataUrl, mapTilePx)) || dataUrl;
        await saveMapAvatar(dataUrl, "upload");
      } catch (e) {
        window.alert(e.message || e);
      }
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  });
  // load existing
  fetch("/api/map-avatar")
    .then((r) => r.json())
    .then((d) => {
      if (d.data_url) {
        mapAvatarUrl = d.data_url;
        localStorage.setItem("morkyn-map-avatar", mapAvatarUrl);
        updateMapAvatarPreview(mapAvatarUrl);
      }
      if (d.tile_px === 16 || d.tile_px === 32) {
        mapTilePx = d.tile_px;
        if (tileSel) tileSel.value = String(mapTilePx);
      }
    })
    .catch(() => {
      if (mapAvatarUrl) updateMapAvatarPreview(mapAvatarUrl);
    });
}

function renderSettlementList(settlements) {
  const list = document.querySelector("#settlementList");
  if (!list) return;
  if (!settlements.length) {
    list.innerHTML = `<p class="empty">No settlements marked yet.</p>`;
    return;
  }
  list.innerHTML = settlements
    .map(
      (s) => `
      <button type="button" class="settlementChip" data-sx="${escapeHtml(s.x)}" data-sy="${escapeHtml(s.y)}" data-sname="${escapeHtml(s.name || s.state)}">
        <strong>${escapeHtml(s.name || s.state)}</strong>
        <span> · (${escapeHtml(s.x)},${escapeHtml(s.y)})</span>
      </button>`
    )
    .join("");
  list.querySelectorAll(".settlementChip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const x = Number(btn.getAttribute("data-sx"));
      const y = Number(btn.getAttribute("data-sy"));
      const s = (fullMapView?.settlements || []).find((row) => Number(row.x) === x && Number(row.y) === y);
      showSettlementDetail(s || { x, y, name: btn.getAttribute("data-sname") });
    });
  });
}

function showSettlementDetail(s) {
  const panel = document.querySelector("#settlementDetail");
  if (!panel || !s) return;
  panel.classList.remove("hidden");
  document.querySelector("#settlementDetailName").textContent = s.name || s.state || "Place";
  document.querySelector("#settlementDetailMeta").textContent = `${s.state || s.kind || "tile"} · (${s.x}, ${s.y})`;
  document.querySelector("#settlementDetailSummary").textContent =
    s.summary || "No extra notes yet. Explore in play to grow this entry.";
  const walk = document.querySelector("#settlementWalkBtn");
  if (walk) {
    walk.disabled = !travelReady;
    walk.onclick = () => walkToTile(Number(s.x), Number(s.y));
  }
}

async function walkToTile(x, y) {
  try {
    const res = await fetch("/api/tiles/map/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    if (data.state) renderShell(data.state);
    updateTravelStatus(data.travel_ready);
    fullMapView = data.map || fullMapView;
    if (fullMapView) {
      await paintTileGrid(document.querySelector("#fullMapCanvas"), fullMapView.tiles || [], {
        tilePx: mapTilePx,
        cell: mapTilePx,
        fog: true,
        mode: "full",
        avatarUrl: mapAvatarUrl,
      });
      renderSettlementList(fullMapView.settlements || []);
    }
    await refreshLocalMap();
    if (latestOutput) {
      latestOutput.innerHTML =
        paragraphs(`You set out toward (${x}, ${y}). Travel closes until the next scene resolves.`) +
        (latestOutput.innerHTML || "");
    }
  } catch (error) {
    window.alert(error.message || String(error));
  }
}

function openMapOverlay() {
  const overlay = document.querySelector("#mapOverlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  refreshFullMap();
  fetch("/api/travel-status")
    .then((r) => r.json())
    .then((d) => updateTravelStatus(d.travel_ready))
    .catch(() => {});
}

function closeMapOverlay() {
  const overlay = document.querySelector("#mapOverlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
}

function bindFullMapHover() {
  const canvas = document.querySelector("#fullMapCanvas");
  const tip = document.querySelector("#mapHoverTip");
  if (!canvas || canvas.dataset.hoverBound === "1") return;
  canvas.dataset.hoverBound = "1";
  canvas.addEventListener("mousemove", (event) => {
    if (!fullMapView || !canvas._mapMeta) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = Math.floor(((event.clientX - rect.left) * scaleX) / canvas._mapMeta.cell) + canvas._mapMeta.minX;
    const cy = Math.floor(((event.clientY - rect.top) * scaleY) / canvas._mapMeta.cell) + canvas._mapMeta.minY;
    const tile = (fullMapView.tiles || []).find((t) => Number(t.x) === cx && Number(t.y) === cy);
    const settle = (fullMapView.settlements || []).find((s) => Number(s.x) === cx && Number(s.y) === cy);
    if (!tile || (tile.fog && !tile.visited && !tile.is_player)) {
      tip?.classList.add("hidden");
      return;
    }
    const label = settle
      ? `${settle.name} (${settle.state || "settlement"})`
      : `${tile.state || "tile"}${tile.visited ? " · visited" : ""}`;
    if (tip) {
      tip.textContent = `${label} · (${cx},${cy})`;
      tip.style.left = `${event.clientX - rect.left + 12}px`;
      tip.style.top = `${event.clientY - rect.top + 12}px`;
      tip.classList.remove("hidden");
    }
  });
  canvas.addEventListener("mouseleave", () => tip?.classList.add("hidden"));
  canvas.addEventListener("click", (event) => {
    if (!fullMapView || !canvas._mapMeta) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = Math.floor(((event.clientX - rect.left) * scaleX) / canvas._mapMeta.cell) + canvas._mapMeta.minX;
    const cy = Math.floor(((event.clientY - rect.top) * scaleY) / canvas._mapMeta.cell) + canvas._mapMeta.minY;
    const settle = (fullMapView.settlements || []).find((s) => Number(s.x) === cx && Number(s.y) === cy);
    if (settle) {
      showSettlementDetail(settle);
      return;
    }
    if (travelReady) {
      const tile = (fullMapView.tiles || []).find((t) => Number(t.x) === cx && Number(t.y) === cy);
      if (tile && tile.walkable !== false && !tile.fog) {
        if (window.confirm(`Walk to (${cx}, ${cy})?`)) walkToTile(cx, cy);
      }
    }
  });
}

function localNpcsFromState() {
  if (!state) return [];
  const loc = state.current_location || {};
  const code = loc.code;
  const fromTree = [];
  for (const place of state.locations || []) {
    if (code && place.code !== code && place.id !== loc.id) continue;
    for (const npc of place.npcs || []) fromTree.push(npc);
  }
  // de-dupe by code/name
  const seen = new Set();
  const out = [];
  for (const npc of fromTree) {
    const key = String(npc.code || npc.name || "").toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(npc);
  }
  return out;
}

function refreshNpcStage() {
  const select = document.querySelector("#npcStageSelect");
  const npcs = localNpcsFromState();
  if (!select) return;
  const prev = focusedNpcCode || select.value;
  if (!npcs.length) {
    select.innerHTML = `<option value="">No one nearby</option>`;
    focusedNpcCode = "";
    setNpcStageFocus(null);
    return;
  }
  select.innerHTML = npcs
    .map((n) => `<option value="${escapeHtml(n.code || n.name)}">${escapeHtml(n.name || n.code)}</option>`)
    .join("");
  const match = npcs.find((n) => (n.code || n.name) === prev) || npcs[0];
  focusedNpcCode = match.code || match.name || "";
  select.value = focusedNpcCode;
  setNpcStageFocus(match);
}

function setNpcStageFocus(npc) {
  const nameEl = document.querySelector("#npcStageName");
  const roleEl = document.querySelector("#npcStageRole");
  const sumEl = document.querySelector("#npcStageSummary");
  const frame = document.querySelector("#npcPortraitFrame");
  if (!npc) {
    if (nameEl) nameEl.textContent = "—";
    if (roleEl) roleEl.textContent = "";
    if (sumEl) sumEl.textContent = "No NPCs at this location.";
    if (frame) {
      frame.classList.add("artDropZone");
      frame.setAttribute("data-art-slot", "npc");
      frame.innerHTML = `<div class="npcPortraitPlaceholder"><span>No one in focus</span><small>drop image</small></div>`;
    }
    return;
  }
  focusedNpcCode = npc.code || npc.name || "";
  if (nameEl) nameEl.textContent = npc.name || "Unknown";
  if (roleEl) roleEl.textContent = [npc.race, npc.role, npc.rank].filter(Boolean).join(" · ");
  if (sumEl) sumEl.textContent = npc.summary || npc.personality || "No notes yet.";
  const cached = npcPortraitCache[focusedNpcCode];
  if (frame) {
    frame.classList.add("artDropZone");
    frame.setAttribute("data-art-slot", "npc");
    frame.setAttribute("data-npc-key", focusedNpcCode);
    if (cached) {
      setArtFrameContent(frame, {
        slot: "npc",
        hasArt: true,
        html: `<img src="${cached}" alt="${escapeHtml(npc.name || "NPC")}" draggable="true" />`,
      });
    } else {
      setArtFrameContent(frame, {
        hasArt: false,
        html: `<div class="npcPortraitPlaceholder"><span>${escapeHtml((npc.name || "?").slice(0, 1).toUpperCase())}</span><br/><small>drop / gen</small></div>`,
      });
    }
  }
}

/** Infer a player-facing visibility note from NPC fields (no inventing a full look). */
function npcVisibilityPayload(npc) {
  if (!npc) return {};
  const note = String(
    npc.visibility_note || npc.player_visibility || npc.seen_as || "",
  ).trim();
  const known = Array.isArray(npc.known_facts)
    ? npc.known_facts.filter(Boolean).slice(0, 6).join("; ")
    : String(npc.known_facts || "");
  const observed = String(
    npc.observed_description || npc.appearance || known || npc.summary || "",
  ).trim();
  const blob = `${note} ${observed}`.toLowerCase();
  const partialMarkers = [
    "silhouette",
    "shadow",
    "glimpse",
    "through a",
    "through the",
    "drain",
    "grate",
    "fog",
    "obscured",
    "hooded",
    "masked",
    "distant",
    "outline",
    "crack",
    "keyhole",
    "barely",
    "half-seen",
    "not fully",
  ];
  const noneMarkers = [
    "not visible",
    "cannot see",
    "can't see",
    "out of sight",
    "unseen",
    "voice only",
    "heard only",
    "another room",
  ];
  let visibility_note = note;
  if (!visibility_note && noneMarkers.some((m) => blob.includes(m))) {
    visibility_note = observed || "Not visible to the player.";
  } else if (!visibility_note && partialMarkers.some((m) => blob.includes(m))) {
    visibility_note = observed.slice(0, 280) || "Only a limited glimpse is visible.";
  }
  return {
    visibility_note,
    observed_description: observed,
  };
}

async function generateNpcPortrait(npc, options = {}) {
  if (!npc) return null;
  const quiet = !!options.quiet;
  const key = npc.code || npc.name || "";
  const frame = document.querySelector("#npcPortraitFrame");
  const focused = focusedNpcCode && (focusedNpcCode === key);
  const vis = npcVisibilityPayload(npc);
  // Auto-gen: name + race/role/summary is enough; don't block on strict observed gates.
  const hasCue = !!(
    npc.name ||
    npc.race ||
    npc.role ||
    (npc.summary || "").trim().length >= 12 ||
    vis.observed_description
  );
  if (!hasCue) {
    if (!quiet && frame && focused) {
      frame.innerHTML = `<div class="npcPortraitPlaceholder"><span>Blocked</span><small>Nothing to draw yet</small></div>`;
    }
    return null;
  }
  if (!imageConfig?.enabled && !quiet) {
    showImageMissingModal({
      missing: [{ code: "backend_off", title: "Image backend is off", detail: "Enable Forge/Comfy/Demo under Images." }],
    });
    return null;
  }
  if (frame && focused) {
    frame.innerHTML = `<div class="npcPortraitPlaceholder"><span>Generating…</span><small>${vis.visibility_note ? "partial" : "portrait"}</small></div>`;
  }
  try {
    const res = await fetch("/api/image/npc-portrait", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: npc.code || "",
        name: npc.name || "",
        role: npc.role || "",
        race: npc.race || "",
        summary: npc.summary || "",
        personality: npc.personality || "",
        visibility_note: vis.visibility_note || "",
        observed_description: vis.observed_description || [npc.race, npc.role, npc.summary].filter(Boolean).join(", "),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail && typeof data.detail === "object" ? data.detail : { error: data.detail || data.error || "Portrait failed" };
      if (!quiet) showImageMissingModal(detail);
      throw new Error(typeof detail.error === "string" ? detail.error : "Portrait failed");
    }
    const url = data.data_url || "";
    if (url) {
      npcPortraitCache[key] = url;
      try {
        const stored = JSON.parse(localStorage.getItem("morkyn-npc-portraits") || "{}");
        stored[key] = url;
        localStorage.setItem("morkyn-npc-portraits", JSON.stringify(stored));
      } catch (_) {
        /* quota */
      }
      if (focused) setNpcStageFocus(npc);
    }
    return url;
  } catch (error) {
    if (frame && focused) {
      frame.innerHTML = `<div class="npcPortraitPlaceholder"><span>${escapeHtml(error.message || String(error))}</span></div>`;
    }
    return null;
  }
}

/** Load cached NPC portraits from localStorage once. */
function hydrateNpcPortraitCache() {
  try {
    const stored = JSON.parse(localStorage.getItem("morkyn-npc-portraits") || "{}");
    if (stored && typeof stored === "object") {
      Object.assign(npcPortraitCache, stored);
    }
  } catch (_) {
    /* ignore */
  }
}

const npcAutoGenQueued = new Set();

/**
 * When auto_generate_npc_portraits is on, generate portraits for newly seen NPCs.
 * Never touches the player character.
 */
function queueAutoNpcPortraits() {
  if (!state?.setup_complete) return;
  if (!imageConfig?.enabled || !imageConfig?.auto_generate_npc_portraits) return;
  if (imageConfig.provider === "off") return;
  const npcs = localNpcsFromState();
  for (const npc of npcs) {
    const key = npc.code || npc.name;
    if (!key) continue;
    if (npcPortraitCache[key]) continue;
    if (npcAutoGenQueued.has(key)) continue;
    // Skip if not visible at all
    const vis = npcVisibilityPayload(npc);
    if (vis.visibility_note && /voice only|not visible|unseen|out of sight/i.test(vis.visibility_note)) continue;
    npcAutoGenQueued.add(key);
    enqueueGpuTask(async () => {
      try {
        await generateNpcPortrait(npc, { quiet: true });
      } finally {
        npcAutoGenQueued.delete(key);
      }
    }, `NPC portrait: ${npc.name || key}`);
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Could not read image file"));
    reader.readAsDataURL(file);
  });
}

async function applyDroppedArtImage(slot, dataUrl) {
  if (!dataUrl || !String(dataUrl).startsWith("data:image")) {
    throw new Error("Drop a PNG/JPEG/WebP image.");
  }
  if (slot === "face" || slot === "setup-face") {
    lastSetupFaceDataUrl = dataUrl;
    setArtFrameContent(document.querySelector("[data-setup-face]"), {
      badge: "face",
      slot: "face",
      hasArt: true,
      html: `<img class="portraitImage" src="${dataUrl}" alt="Character face" draggable="true" />`,
    });
    localStorage.setItem("morkyn-player-portrait", dataUrl);
    setSetupArtStatus("Face set from drop.");
    return;
  }
  if (slot === "fullbody" || slot === "setup-fullbody") {
    lastSetupBodyDataUrl = dataUrl;
    setArtFrameContent(document.querySelector("[data-setup-fullbody]"), {
      badge: "body · 3:4",
      slot: "fullbody",
      hasArt: true,
      html: `<img class="portraitImage portraitImageFull" src="${dataUrl}" alt="Character full body" draggable="true" />`,
    });
    localStorage.setItem("morkyn-player-fullbody", dataUrl);
    setSetupArtStatus("Full body set from drop.");
    return;
  }
  if (slot === "player-face") {
    localStorage.setItem("morkyn-player-portrait", dataUrl);
    localStorage.setItem("morkyn-player-portrait-sig", playerPortraitSignature());
    if (state) state.player_portrait = { data_url: dataUrl, kind: "face" };
    lastSetupFaceDataUrl = dataUrl;
    setArtFrameContent(document.querySelector("#playerFaceFrame"), {
      slot: "player-face",
      hasArt: true,
      html: `<img src="${dataUrl}" alt="Player face" draggable="true" />`,
    });
    setPlayerArtStatus("Face set from drop.");
    return;
  }
  if (slot === "player-fullbody") {
    localStorage.setItem("morkyn-player-fullbody", dataUrl);
    if (state) state.player_fullbody = { data_url: dataUrl, kind: "fullbody" };
    lastSetupBodyDataUrl = dataUrl;
    setArtFrameContent(document.querySelector("#playerFullbodyFrame"), {
      slot: "player-fullbody",
      hasArt: true,
      html: `<img src="${dataUrl}" alt="Player full body" draggable="true" />`,
    });
    setPlayerArtStatus("Full body set from drop.");
    return;
  }
  if (slot === "npc") {
    const key = focusedNpcCode || document.querySelector("#npcPortraitFrame")?.getAttribute("data-npc-key");
    if (!key) throw new Error("No NPC in focus.");
    npcPortraitCache[key] = dataUrl;
    try {
      const stored = JSON.parse(localStorage.getItem("morkyn-npc-portraits") || "{}");
      stored[key] = dataUrl;
      localStorage.setItem("morkyn-npc-portraits", JSON.stringify(stored));
    } catch (_) {
      /* ignore */
    }
    const npc = localNpcsFromState().find((n) => (n.code || n.name) === key);
    if (npc) setNpcStageFocus(npc);
    else {
      setArtFrameContent(document.querySelector("#npcPortraitFrame"), {
        slot: "npc",
        hasArt: true,
        html: `<img src="${dataUrl}" alt="NPC" draggable="true" />`,
      });
    }
  }
}

function bindArtDropZones() {
  if (document.body.dataset.artDropBound === "1") return;
  document.body.dataset.artDropBound = "1";

  document.addEventListener("dragover", (event) => {
    const zone = event.target.closest?.(".artDropZone, [data-art-slot], #npcPortraitFrame, [data-setup-face], [data-setup-fullbody], #playerFaceFrame, #playerFullbodyFrame");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("artDropHover");
  });

  document.addEventListener("dragleave", (event) => {
    const zone = event.target.closest?.(".artDropZone, [data-art-slot]");
    if (zone) zone.classList.remove("artDropHover");
  });

  document.addEventListener("drop", (event) => {
    const zone = event.target.closest?.(
      ".artDropZone, [data-art-slot], #npcPortraitFrame, [data-setup-face], [data-setup-fullbody], #playerFaceFrame, #playerFullbodyFrame",
    );
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("artDropHover");
    let slot =
      zone.getAttribute("data-art-slot") ||
      (zone.matches("[data-setup-face]") ? "face" : "") ||
      (zone.matches("[data-setup-fullbody]") ? "fullbody" : "") ||
      (zone.id === "playerFaceFrame" ? "player-face" : "") ||
      (zone.id === "playerFullbodyFrame" ? "player-fullbody" : "") ||
      (zone.id === "npcPortraitFrame" ? "npc" : "");
    const file = [...(event.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
    const portraitId =
      event.dataTransfer?.getData("application/x-morkyn-portrait") ||
      event.dataTransfer?.getData("text/x-morkyn-portrait") ||
      "";
    const uri = event.dataTransfer?.getData("text/uri-list") || event.dataTransfer?.getData("text/plain") || "";
    if (file) {
      readFileAsDataUrl(file)
        .then((url) => applyDroppedArtImage(slot, url))
        .catch((err) => window.alert(err.message || String(err)));
      return;
    }
    if (portraitId) {
      const asFace = slot === "fullbody" || slot === "player-fullbody" || slot === "setup-fullbody" ? "fullbody" : "face";
      applyNativePortraitToSlot(portraitId, asFace).catch((err) => window.alert(err.message || String(err)));
      return;
    }
    if (uri && uri.startsWith("data:image")) {
      applyDroppedArtImage(slot, uri.trim()).catch((err) => window.alert(err.message || String(err)));
      return;
    }
    // Same-origin portrait file URL from library thumb
    if (uri && (uri.includes("/api/portraits/file") || uri.includes("portraits/file"))) {
      try {
        const u = new URL(uri, window.location.origin);
        const name = u.searchParams.get("name");
        if (name) {
          const asFace = slot === "fullbody" || slot === "player-fullbody" || slot === "setup-fullbody" ? "fullbody" : "face";
          applyNativePortraitToSlot(name, asFace).catch((err) => window.alert(err.message || String(err)));
        }
      } catch (_) {
        /* ignore bad uri */
      }
    }
  });

  // Drag library thumbs or existing slot images onto face/body frames.
  document.addEventListener("dragstart", (event) => {
    const img = event.target.closest?.("img");
    if (!img) return;
    const portraitId =
      img.getAttribute("data-portrait-drag-id") ||
      img.closest("[data-portrait-id]")?.getAttribute("data-portrait-id") ||
      "";
    if (portraitId) {
      event.dataTransfer?.setData("application/x-morkyn-portrait", portraitId);
      event.dataTransfer?.setData("text/x-morkyn-portrait", portraitId);
      event.dataTransfer?.setData("text/uri-list", img.src || "");
      event.dataTransfer?.setData("text/plain", portraitId);
      event.dataTransfer.effectAllowed = "copy";
      return;
    }
    if (!img.src?.startsWith("data:")) return;
    const zone = img.closest(".artDropZone, [data-art-slot], #npcPortraitFrame");
    if (!zone) return;
    event.dataTransfer?.setData("text/uri-list", img.src);
    event.dataTransfer?.setData("text/plain", img.src);
    event.dataTransfer.effectAllowed = "copy";
  });
}

function openNpcRoster() {
  const modal = document.querySelector("#npcRosterModal");
  const list = document.querySelector("#npcRosterList");
  if (!modal || !list) return;
  const npcs = localNpcsFromState();
  list.innerHTML = npcs.length
    ? npcs
        .map((n) => {
          const key = n.code || n.name;
          const img = npcPortraitCache[key];
          return `
          <article class="npcRosterCard" data-npc-key="${escapeHtml(key)}">
            <div class="thumb">${img ? `<img src="${img}" alt="" />` : escapeHtml((n.name || "?").slice(0, 1))}</div>
            <strong>${escapeHtml(n.name || key)}</strong>
            <span class="empty">${escapeHtml([n.race, n.role].filter(Boolean).join(" · ") || "local")}</span>
          </article>`;
        })
        .join("")
    : `<p class="empty">No NPCs at this location.</p>`;
  list.querySelectorAll(".npcRosterCard").forEach((card) => {
    card.addEventListener("click", () => {
      const key = card.getAttribute("data-npc-key");
      const npc = localNpcsFromState().find((n) => (n.code || n.name) === key);
      if (npc) {
        const select = document.querySelector("#npcStageSelect");
        if (select) select.value = key;
        setNpcStageFocus(npc);
      }
      modal.classList.add("hidden");
    });
  });
  modal.classList.remove("hidden");
}

document.querySelector("#openMapOverlayBtn")?.addEventListener("click", () => openMapOverlay());
document.querySelector("#sideOpenMapBtn")?.addEventListener("click", () => openMapOverlay());
document.querySelector("#closeMapOverlayBtn")?.addEventListener("click", () => closeMapOverlay());
document.querySelector("#settlementDetailClose")?.addEventListener("click", () => {
  document.querySelector("#settlementDetail")?.classList.add("hidden");
});
document.querySelector("#npcStageSelect")?.addEventListener("change", (event) => {
  const key = event.target.value;
  const npc = localNpcsFromState().find((n) => (n.code || n.name) === key);
  setNpcStageFocus(npc || null);
});
document.querySelector("#npcPortraitBtn")?.addEventListener("click", () => {
  const npc = localNpcsFromState().find((n) => (n.code || n.name) === focusedNpcCode);
  generateNpcPortrait(npc);
});
document.querySelector("#npcTalkBtn")?.addEventListener("click", () => {
  const npc = localNpcsFromState().find((n) => (n.code || n.name) === focusedNpcCode);
  if (!npc || !turnInput) return;
  turnInput.value = `I speak with ${npc.name}.`;
  turnInput.focus();
});
document.querySelector("#npcRosterBtn")?.addEventListener("click", () => openNpcRoster());
document.querySelector("#closeNpcRoster")?.addEventListener("click", () => {
  document.querySelector("#npcRosterModal")?.classList.add("hidden");
});
document.querySelector("#npcRosterModal")?.addEventListener("click", (event) => {
  if (event.target?.id === "npcRosterModal") event.target.classList.add("hidden");
});
bindFullMapHover();

// Patch displayTurnPayload travel flag
const _displayTurnPayloadOrig = typeof displayTurnPayload === "function" ? displayTurnPayload : null;
if (_displayTurnPayloadOrig) {
  displayTurnPayload = function patchedDisplayTurnPayload(payload, options = {}) {
    const ok = _displayTurnPayloadOrig(payload, options);
    if (payload && "travel_ready" in payload) updateTravelStatus(payload.travel_ready);
    else if (payload?.travel && "ready" in payload.travel) updateTravelStatus(payload.travel.ready);
    refreshLocalMap();
    refreshNpcStage();
    return ok;
  };
}


// ---- Main menu + app settings --------------------------------------------
async function loadAppSettingsForm() {
  const form = document.querySelector("#appSettingsForm");
  if (!form) return;
  try {
    const res = await fetch("/api/launcher-prefs", { cache: "no-store" });
    const data = await res.json();
    const prefs = data.prefs || {};
    Object.entries(prefs).forEach(([key, value]) => {
      if (key === "narration_pipeline" || key === "narration_consolidate" || key === "fast_verification") {
        const on = Boolean(value);
        const radio = form.querySelector(`input[name="${key}"][value="${on}"]`);
        if (radio) radio.checked = true;
        return;
      }
      const el = form.elements[key];
      if (el && el.type !== "radio") el.value = value == null ? "" : String(value);
    });
    if (prefs.ui_theme) {
      document.documentElement.setAttribute("data-theme", prefs.ui_theme);
      const themeSel = document.querySelector("#themeSelect");
      if (themeSel) themeSel.value = prefs.ui_theme;
    }
  } catch (error) {
    const st = document.querySelector("#appSettingsStatus");
    if (st) st.textContent = `Could not load prefs: ${error.message || error}`;
  }
}

function openAppSettings() {
  const modal = document.querySelector("#appSettingsModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  // Ensure visibility even if an old stylesheet omitted :not(.hidden) rules
  if (getComputedStyle(modal).display === "none") {
    modal.style.display = "grid";
  }
  loadAppSettingsForm();
}

function closeAppSettings() {
  const modal = document.querySelector("#appSettingsModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "";
}

function resetSetupTutorialFromSettings() {
  try {
    // Clear all known tutorial keys so any version re-triggers
    for (let i = 1; i <= 20; i += 1) {
      localStorage.removeItem(`morkyn-setup-tutorial-v${i}`);
    }
    localStorage.removeItem(SETUP_TUTORIAL_KEY);
    localStorage.removeItem(ART_GUIDE_KEY);
    for (let i = 1; i <= 10; i += 1) {
      localStorage.removeItem(`morkyn-art-guide-v${i}`);
    }
  } catch (_) {
    /* ignore */
  }
  const st = document.querySelector("#appSettingsStatus");
  if (st) st.textContent = "Setup tutorial + art guide reset. Open Start new game to see them again.";
  closeAppSettings();
  // Jump into setup with tour forced
  showSetupWizard({ forceTutorial: true });
}

document.querySelector("#menuNewGame")?.addEventListener("click", () => showSetupWizard());
document.querySelector("#menuContinue")?.addEventListener("click", (event) => {
  event.preventDefault();
  if (event.currentTarget?.disabled) return;
  continuePlaythrough();
});
document.querySelector("#menuLoadGame")?.addEventListener("click", () => {
  try {
    openSaveBrowser("load");
  } catch (error) {
    const status = document.querySelector("#mainMenuStatus");
    if (status) status.textContent = error.message || String(error);
  }
});
document.querySelector("#menuSettings")?.addEventListener("click", (event) => {
  event.preventDefault();
  openAppSettings();
});
document.querySelector("#closeAppSettings")?.addEventListener("click", () => closeAppSettings());
document.querySelector("#appSettingsModal")?.addEventListener("click", (event) => {
  if (event.target?.id === "appSettingsModal") closeAppSettings();
});
document.querySelector("#settingsOpenLlm")?.addEventListener("click", () => {
  closeAppSettings();
  openModelModalFromUi().catch((error) => {
    if (modelModalContent) {
      modelModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    }
  });
});
document.querySelector("#settingsResetTutorial")?.addEventListener("click", () => {
  resetSetupTutorialFromSettings();
});
document.querySelector("#settingsReloadUi")?.addEventListener("click", () => {
  window.location.reload();
});
document.querySelector("#setupBackMenu")?.addEventListener("click", () => showMainMenu());
document.querySelector("#appSettingsForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const fd = new FormData(form);
  const prefs = {
    launch_mode: fd.get("launch_mode"),
    app_port: Number(fd.get("app_port") || 8000),
    model_provider: fd.get("model_provider"),
    ollama_model: fd.get("ollama_model"),
    ollama_base_url: fd.get("ollama_base_url"),
    gguf_model_path: fd.get("gguf_model_path"),
    api_base_url: fd.get("api_base_url"),
    api_model: fd.get("api_model"),
    ui_theme: fd.get("ui_theme"),
    narration_pipeline: fd.get("narration_pipeline") === "true",
    narration_consolidate: fd.get("narration_consolidate") === "true",
    fast_verification: fd.get("fast_verification") === "true",
  };
  const st = document.querySelector("#appSettingsStatus");
  try {
    const res = await fetch("/api/launcher-prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prefs, apply_env: true }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Save failed");
    if (prefs.ui_theme) {
      document.documentElement.setAttribute("data-theme", prefs.ui_theme);
      localStorage.setItem("morkyn-ui-theme", prefs.ui_theme);
      const themeSel = document.querySelector("#themeSelect");
      if (themeSel) themeSel.value = prefs.ui_theme;
    }
    if (st) st.textContent = "Saved & applied. Port/reach need a full app restart from Morkyn.bat if changed.";
  } catch (error) {
    if (st) st.textContent = error.message || String(error);
  }
});

decorateSetupFields();
ensureTextAiControls();
renderDirectorPresets();
decorateFunctionHelp();
bindSetupNavExtras();
bindSetupMoreTools();
bindTabCategoryNav();
setSetupStep(0);
updateConditionalSetup();
updateComposerState();
loadSkillCatalog().catch(() => {});
bindPlayLayoutControls();
applyPlayLayout();
// Boot: main menu first; setup only after "Start new game"
// Never leave LLM modal open from a prior checkbox state / CSS race.
closeModelModalFromUi();
showMainMenu();
loadState()
  .then(() => {
    // Stay on menu unless user continues; only reveal Continue if a game exists.
    showMainMenu();
    applyPlayLayout();
  })
  .catch((error) => {
    showMainMenu();
    const status = document.querySelector("#mainMenuStatus");
    if (status) status.textContent = error.message || String(error);
  });


