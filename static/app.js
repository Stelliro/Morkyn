const setupView = document.querySelector("#setupView");
const gameView = document.querySelector("#gameView");
const setupForm = document.querySelector("#setupForm");
const setupSections = Array.from(document.querySelectorAll(".setupSection"));
const setupStepButtons = Array.from(document.querySelectorAll("[data-setup-step]"));
const setupPrevButton = document.querySelector("#setupPrev");
const setupNextButton = document.querySelector("#setupNext");
const setupStepStatus = document.querySelector("#setupStepStatus");
const setupModelButton = document.querySelector("#setupModelButton");
const setupStartButton = document.querySelector("#setupStart");
const saveSetupSettingsButton = document.querySelector("#saveSetupSettings");
const setupSettingsFile = document.querySelector("#setupSettingsFile");
const randomizeSetup = document.querySelector("#randomizeSetup");
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
const modelButton = document.querySelector("#modelButton");
const importFile = document.querySelector("#importFile");
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
  player_sex: ["", "female", "male", "intersex", "sexless or constructed", "varies by form"],
  previous_life_age: ["19", "27", "34", "46", "elderly", "unknown"],
  previous_life_sex: ["", "female", "male", "intersex", "sexless or constructed", "varies by form"],
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

const ABILITY_PRESETS = [
  {
    name: "Echo Step",
    description: "A short burst of impossible movement, useful for escapes or sudden positioning.",
    locked: false,
    prerequisites: "",
    cost: "",
  },
  {
    name: "Ashen Oath",
    description: "Can sense when someone nearby is hiding a binding promise or unpaid debt.",
    locked: true,
    prerequisites: "Awakens after witnessing a broken oath with real consequences.",
    cost: "",
  },
  {
    name: "Thread Sense",
    description: "Briefly notices the emotional weight attached to an object or place.",
    locked: false,
    prerequisites: "",
    cost: "Brief fatigue or sensory overload after repeated use.",
  },
  {
    name: "Last Light",
    description: "Survives one fatal mistake as a lasting injury instead of immediate death.",
    locked: true,
    prerequisites: "Only unlocks after the player accepts a serious personal risk.",
    cost: "One permanent scar, debt, or consequence chosen by context.",
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
  character: ["backstory_mode", "memory_policy", "character_backstory", "player_name", "player_public_name", "player_title", "player_age", "player_sex", "previous_life_age", "previous_life_sex", "special_ability_origin", "special_abilities"],
  world: ["world_style", "magic_level", "world_races", "race_magic_enabled", "race_magic_rarity", "tech_level", "tone", "economy", "start_location", "custom_style", "race_magic_rules", "race_ability_rules"],
  people: ["npc_density", "quest_style", "faction_pressure", "npc_stat_scaling", "npc_skill_frequency", "rank_scale"],
  rules: ["difficulty", "death_rules", "narration_detail", "loot_rarity", "inventory_weight_limit", "inventory_slot_limit", "inventory_rules", "leveling_system", "game_system", "proficiency_system", "skill_levels_enabled", "skill_style", "proficiency_access", "new_skill_frequency", "xp_growth_speed", "skill_growth_speed", "proficiency_growth_speed", "system_style", "custom_skills"],
};

const RANDOM_GROUP_ORDER = ["character", "world", "people", "rules"];
const RANDOM_FIELD_ORDER = [
  "backstory_mode",
  "world_style",
  "magic_level",
  "world_races",
  "race_magic_enabled",
  "race_magic_rarity",
  "tech_level",
  "tone",
  "economy",
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
  "memory_policy",
  "start_location",
  "custom_style",
  "race_magic_rules",
  "race_ability_rules",
  "npc_density",
  "quest_style",
  "faction_pressure",
  "npc_stat_scaling",
  "npc_skill_frequency",
  "rank_scale",
  "character_backstory",
  "player_name",
  "player_public_name",
  "player_title",
  "player_age",
  "player_sex",
  "previous_life_age",
  "previous_life_sex",
  "special_ability_origin",
  "custom_skills",
  "special_abilities",
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
    description: "The character's current biological sex or body category when it matters to the setting. Leave blank when irrelevant or unknown.",
    customPlaceholder: "Example: changes with moon phase, not applicable, unknown to player",
  },
  previous_life_age: {
    description: "For reincarnated or transmigrated starts, the age the character remembers from the former life.",
  },
  previous_life_sex: {
    description: "For reincarnated or transmigrated starts, the sex or body category remembered from the former life.",
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
    description: "Comma-separated custom proficiencies or training-rule phrases. Use commas between each proficiency; commas are treated as the separator when settings are saved, loaded, randomized, or started.",
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
  skill_style: 60,
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
  ["#randomizeSetup", "Randomize the whole setup in dependency order. Locked fields are skipped, and dependent fields wait for their parent toggle."],
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
  "Character setup: identity, backstory mode, memory rules, and starting special abilities.",
  "World setup: genre, start location, races, magic access, technology, tone, and setting constraints.",
  "People setup: NPC density, quest style, factions, rank scale, and how trained NPCs tend to be.",
  "Rules setup: difficulty, death rules, narration detail, loot, inventory limits, leveling, skills, proficiencies, and in-world system UI.",
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
    ensureHelpForTarget(button, RANDOM_GROUP_HELP[group] || "Randomize this setup group while respecting locked fields.");
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

function clearTurnWaitTimer() {
  if (turnWaitTimer) {
    window.clearInterval(turnWaitTimer);
    turnWaitTimer = null;
  }
}

function updateTurnWaitPanel(startedAt, kind) {
  const elapsed = document.querySelector("#turnWaitElapsed");
  const text = document.querySelector("#turnWaitText");
  if (!elapsed || !text) return;
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const messages = TURN_WAIT_REASSURANCE[kind] || TURN_WAIT_REASSURANCE.turn;
  elapsed.textContent = `Elapsed ${elapsedLabel(startedAt)}`;
  text.textContent = messages[Math.floor(elapsedSeconds / 10) % messages.length];
}

function showTurnWaitPanel(title, kind = "turn") {
  clearTurnWaitTimer();
  if (!latestOutput) return;
  const startedAt = Date.now();
  latestOutput.innerHTML = `
    <div class="turnWaitPanel" role="status" aria-live="polite">
      <div class="turnWaitPulse" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="turnWaitCopy">
        <strong>${escapeHtml(title)}</strong>
        <span id="turnWaitElapsed">Elapsed 0:00</span>
        <p id="turnWaitText"></p>
      </div>
    </div>
  `;
  updateTurnWaitPanel(startedAt, kind);
  turnWaitTimer = window.setInterval(() => updateTurnWaitPanel(startedAt, kind), 1000);
}

function clearStartSplashTimers() {
  startSplashTimers.forEach((timer) => window.clearTimeout(timer));
  startSplashTimers = [];
  if (startSplashHeartbeatTimer) {
    window.clearInterval(startSplashHeartbeatTimer);
    startSplashHeartbeatTimer = null;
  }
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
  const startedAt = Date.now();
  startSplash.classList.remove("hidden");
  if (startSplashLog) startSplashLog.innerHTML = "";
  startSplashHeartbeat?.classList.remove("hidden");
  updateStartSplashHeartbeat(startedAt);
  startSplashHeartbeatTimer = window.setInterval(() => updateStartSplashHeartbeat(startedAt), 1000);
  if (startSplashDraft) {
    startSplashDraft.textContent = "";
    startSplashDraft.classList.remove("startSplashCursor");
  }
  const lines = [
    "Collecting setup rules and locked choices.",
    "Preparing the opening-scene context packet.",
    "Selecting event-worthy focus points for the starting location.",
    "Asking the local model for one continuous opening scene.",
    "Verifier will check references, continuity, and state changes.",
  ];
  lines.forEach((line, index) => {
    startSplashTimers.push(window.setTimeout(() => addStartSplashLine(line), index * 850));
  });
  [
    "Local generation can take a minute on larger models.",
    "Still waiting for the draft; the page is alive.",
    "Verifier pass may be checking the draft now.",
    "Finishing the opening scene and preparing state updates.",
  ].forEach((line, index) => {
    startSplashTimers.push(window.setTimeout(() => addStartSplashLine(line), 9000 + index * 16000));
  });
  startSplashTimers.push(window.setTimeout(() => addStartSplashLine("Still running; the elapsed timer below updates until the server responds."), 73000));
  startSplashTimers.push(window.setTimeout(() => addStartSplashLine("Long waits usually mean model load, first-token delay, or verifier work rather than a frozen page."), 113000));
}

function hideStartSplash() {
  clearStartSplashTimers();
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
  if (setupNextButton && setupStep === setupSections.length - 1) setupNextButton.disabled = nextBusy;
  updateTextOptimizeControls();
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
  aiQueue = aiQueue.catch(() => {}).then(run);
  return aiQueue;
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
    const count = abilityQuantityLocked() ? currentAbilitySlotCount() : rollInt(1, 5);
    abilityList.innerHTML = "";
    for (let i = 0; i < count; i += 1) addAbility(randomAbilityPreset());
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
  if (["player_name", "player_public_name", "player_title", "player_age", "previous_life_age", "character_backstory", "start_location", "custom_style", "race_magic_rules", "race_ability_rules", "custom_skills", "inventory_rules"].includes(name)) {
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
  for (const name of fields) {
    normalizeRandomizerDependencies();
    if (!randomizeFieldApplies(name)) continue;
    await randomizeField(name);
  }
}

async function randomizeField(name, options = {}) {
  if (!options.ignoreLock && isSettingLocked(name)) return;
  const response = await fetch("/api/randomize-setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group: `field:${name}`, current: currentSetupSnapshot(name) }),
  });
  if (!response.ok) throw new Error(await response.text());
  applyRandomizedSetup(await response.json());
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

async function randomizeAllSetup() {
  for (const name of RANDOM_FIELD_ORDER) {
    normalizeRandomizerDependencies();
    if (!randomizeFieldApplies(name)) continue;
    await randomizeField(name);
  }
}

function setSetupStep(nextStep) {
  setupStep = Math.max(0, Math.min(setupSections.length - 1, nextStep));
  setupSections.forEach((section, index) => section.classList.toggle("active", index === setupStep));
  setupStepButtons.forEach((button, index) => button.classList.toggle("active", index === setupStep));
  if (setupPrevButton) setupPrevButton.disabled = setupStep === 0;
  if (setupNextButton) setupNextButton.textContent = setupStep === setupSections.length - 1 ? "Start" : "Next";
  if (setupStepStatus) setupStepStatus.textContent = `Step ${setupStep + 1} of ${setupSections.length}`;
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

function randomAbilityPreset() {
  return { ...choice(ABILITY_PRESETS) };
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
      return { name, description, locked, prerequisites, cost };
    })
    .filter((ability) => ability.name || ability.description);
}

function updateSystemStyleDescription() {
  const description = document.querySelector("#systemStyleDescription");
  const value = setupForm.elements.system_style?.value;
  if (description) description.textContent = SYSTEM_STYLE_DESCRIPTIONS[value] || "";
}

function renderShell(nextState) {
  state = nextState;
  const ready = Boolean(state.setup_complete);
  setupView.classList.toggle("hidden", ready);
  gameView.classList.toggle("hidden", !ready);
  if (!ready) return;

  const location = state.current_location || {};
  locationLine.innerHTML = `${escapeHtml(location.code || "L?")} ${escapeHtml(location.name || "Unknown")} · ${escapeHtml(location.summary || "No notes.")}`;
  renderHistory();
  renderIndex();
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
  return `
    <article class="card">
      <strong>Model Budget</strong>
      <div class="meta">warning at ~${escapeHtml(budget.warning_threshold || "?")} tokens</div>
      <p>${escapeHtml(body)}</p>
      ${warning}
    </article>
  `;
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
  return `
    <div class="statGrid">
      ${statCard("Health", `${player.health ?? 0}/${player.max_health ?? 0}`)}
      ${statCard("Level", options.leveling_system === false ? "Off" : player.level ?? 1)}
      ${statCard("XP", options.leveling_system === false ? "Off" : player.xp ?? 0)}
      ${statCard("Gold", player.gold ?? 0)}
      ${statCard("Karma", player.karma ?? 0)}
    </div>
    ${card("Identity", identityParts.join(" | ") || "No identity details recorded.")}
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
        .map((npc) =>
          entityCard(
            "npc",
            npc,
            npc.summary || "No notes.",
            `${escapeHtml(npc.race || "human")} · ${escapeHtml(npc.role)} · rank ${escapeHtml(npc.rank || "F")} · ${escapeHtml(npc.attitude)} · trust ${escapeHtml(npc.trust ?? 0)} · ${escapeHtml(npc.place)}`,
          ),
        )
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

function renderModelForm() {
  const config = modelConfig || {};
  const provider = config.provider || "llama_cpp";
  return `
    <form id="modelForm" class="modelForm">
      <label>
        <span>Provider</span>
        <select name="provider">
          <option value="llama_cpp" ${provider === "llama_cpp" ? "selected" : ""}>llama.cpp / GGUF</option>
          <option value="ollama" ${provider === "ollama" ? "selected" : ""}>Ollama</option>
        </select>
      </label>
      <label>
        <span>Model Path</span>
        <div class="pathPickerRow">
          <input name="gguf_model_path" value="${escapeHtml(config.gguf_model_path || DEFAULT_GGUF_MODEL)}" maxlength="1000" placeholder="D:\\path\\to\\model.gguf" />
          <button class="secondaryButton selectModelFile" type="button">Select File</button>
        </div>
      </label>
      <label>
        <span>LLM Server URL</span>
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
      <div class="modelButtonRow">
        <button type="submit">Save Model</button>
        <button class="secondaryButton testModelConnection" type="button">Test Connection</button>
      </div>
    </form>
    <div class="modelStatus" data-model-status></div>
    <p class="empty">Select the local model file and the URL of the compatible LLM server that will run it.</p>
  `;
}

function renderModel() {
  return renderModelForm();
}

function renderIndex() {
  const renderers = {
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
  };
  if (!renderers[activeTab]) activeTab = "player";
  indexTabs.querySelectorAll("button").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === activeTab));
  indexContent.innerHTML = renderers[activeTab]();
  decorateFunctionHelp(indexContent);
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

async function openModelModal() {
  if (!modelModal || !modelModalContent) return;
  modelModalContent.innerHTML = paragraphs("Loading model settings...");
  const response = await fetch("/api/model-config");
  if (!response.ok) throw new Error(await response.text());
  modelConfig = await response.json();
  modelModalContent.innerHTML = renderModelForm();
  decorateFunctionHelp(modelModalContent);
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
  if (activeTab === "model" && !gameView.classList.contains("hidden")) renderIndex();
  if (modelModalContent && modelModalToggle?.checked) {
    modelModalContent.innerHTML = `${renderModelForm()}<p class="good">Model settings saved.</p>`;
    decorateFunctionHelp(modelModalContent);
  }
  latestOutput.innerHTML = paragraphs("Model settings saved.");
}

function modelPayloadFromForm(form) {
  const formData = new FormData(form);
  return {
    provider: formData.get("provider") || "llama_cpp",
    gguf_model_path: formData.get("gguf_model_path"),
    llama_cpp_base_url: formData.get("llama_cpp_base_url"),
    ollama_model: formData.get("ollama_model") || "llama3.1",
    ollama_base_url: formData.get("ollama_base_url") || "http://localhost:11434",
    response_token_cap: Math.round(finiteNumber(formData.get("response_token_cap"), 1500)),
    response_token_hard_cap: Math.round(finiteNumber(formData.get("response_token_hard_cap"), 2000)),
  };
}

async function selectModelFile(form) {
  const response = await fetch("/api/select-model-file", { method: "POST" });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  if (payload.path) form.querySelector('[name="gguf_model_path"]').value = payload.path;
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
    body = `
      <p>${escapeHtml(entity.summary || "No summary.")}</p>
      <p><strong>Race:</strong> ${escapeHtml(entity.race || "human")} · <strong>Role:</strong> ${escapeHtml(entity.role)} · <strong>Rank:</strong> ${escapeHtml(entity.rank || "F")} · <strong>Attitude:</strong> ${escapeHtml(entity.attitude)} · <strong>Trust:</strong> ${escapeHtml(entity.trust ?? 0)}</p>
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

function appendTurnMeta(payload) {
  const rewardsHtml = turnRewardsHtml(payload);
  if (rewardsHtml) latestOutput.innerHTML += rewardsHtml;
  const planHtml = scenePlanHtml(payload.turn.scene_plan);
  if (planHtml) latestOutput.innerHTML += planHtml;
  if (payload.turn.self_check) {
    const check = payload.turn.self_check;
    latestOutput.innerHTML += `<section class="selfCheck ${check.passed ? "passed" : "failed"}"><strong>Check:</strong> ${escapeHtml(check.passed ? "passed" : "needs review")} · ${escapeHtml(check.consistency_check || "")}</section>`;
  }
  if (payload.used_fallback) {
    const reason = payload.fallback_reason || payload.turn.llm_error || "No detailed error returned.";
    const notice = payload.fallback_notice || fallbackNoticeText(reason);
    latestOutput.innerHTML += `
      <section class="fallbackNotice">
        <strong>Fallback narration generated.</strong>
        <p>${escapeHtml(notice)}</p>
        <small>Model issue: ${escapeHtml(clipText(reason, 420))}</small>
      </section>
    `;
  }
  if (payload.debug_trace_path) {
    latestOutput.innerHTML += `
      <section class="debugTraceNotice">
        <strong>Debug trace</strong>
        <p>${escapeHtml(payload.debug_trace_path)}</p>
      </section>
    `;
  }
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
    enqueueAiTask(
      withSetupRandomizationLock(
        () => randomizeGroup(randomizer.dataset.randomizeGroup),
        label,
        (error) => {
          fallbackRandomizeSequence(RANDOM_GROUPS[randomizer.dataset.randomizeGroup] || []);
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
  const label = "Randomizing setup...";
  enqueueAiTask(
    withSetupRandomizationLock(
      () => randomizeAllSetup(),
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
    });
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
setupModelButton?.addEventListener("click", () => {
  window.setTimeout(() => {
    if (!modelModalToggle?.checked) return;
    openModelModal().catch((error) => {
      if (modelModalContent) modelModalContent.innerHTML = `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
    });
  }, 0);
});
closeModelModal?.addEventListener("click", (event) => {
  event.preventDefault();
  if (modelModalToggle) modelModalToggle.checked = false;
});
modelModal?.addEventListener("click", (event) => {
  if (event.target === modelModal && modelModalToggle) modelModalToggle.checked = false;
});
modelButton?.addEventListener("click", () => {
  activeTab = "model";
  indexTabs.querySelectorAll("button").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === "model"));
  renderIndex();
  loadModelConfig().catch((error) => (indexContent.innerHTML = paragraphs(error.message)));
});
importFile.addEventListener("change", () => {
  const file = importFile.files?.[0];
  if (file) importWorld(file).catch((error) => (latestOutput.innerHTML = paragraphs(error.message)));
  importFile.value = "";
});
newGameButton.addEventListener("click", () => {
  setupView.classList.remove("hidden");
  gameView.classList.add("hidden");
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

indexTabs.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  activeTab = button.dataset.tab;
  indexTabs.querySelectorAll("button").forEach((tab) => tab.classList.toggle("active", tab === button));
  renderIndex();
  if (activeTab === "bible") loadBible().catch((error) => (indexContent.innerHTML = paragraphs(error.message)));
  if (activeTab === "model") loadModelConfig().catch((error) => (indexContent.innerHTML = paragraphs(error.message)));
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
  if (!modelForm) return;
  event.preventDefault();
  saveModelConfig(modelForm).catch((error) => {
    modelModalContent.innerHTML += `<p class="bad">${escapeHtml(error.message || String(error))}</p>`;
  });
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

decorateSetupFields();
ensureTextAiControls();
decorateFunctionHelp();
setSetupStep(0);
updateConditionalSetup();
updateComposerState();
loadState().catch((error) => {
  setupView.classList.remove("hidden");
  latestOutput.innerHTML = paragraphs(error.message || String(error));
});
