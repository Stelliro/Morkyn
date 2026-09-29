"""
Static world context blocks injected into LLM prompts to ensure consistency.
"""

# Cultural naming patterns (not random syllables)
NAMING_PATTERNS = {
    "nordic": {
        "prefixes": ["Bjorn", "Erik", "Sigrid", "Runa", "Ulf", "Astrid", "Gunnar", "Freya", "Leif", "Ingrid"],
        "suffixes": ["sson", "dottir", "ar", "ir", "mund", "helm", "rik"],
        "compound": ["Iron", "Storm", "Wolf", "Ash", "Frost", "Ember", "Stone", "Tide"],
        "pattern": "{prefix} {compound}{suffix}",
    },
    "eastern": {
        "given": ["Wei", "Lin", "Mei", "Chen", "Bao", "Shu", "Yun", "Feng", "Han", "Xiao"],
        "family": ["Li", "Wang", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou"],
        "title_suffixes": ["-sifu", "-jie", "-ge", "-laoshi"],
        "pattern": "{family} {given}",
    },
    "medieval_english": {
        "given_male": ["Edmund", "Aldric", "Oswin", "Cormac", "Godwin", "Wulfric", "Aelred", "Bertram"],
        "given_female": ["Mildred", "Eadith", "Wynne", "Isolde", "Aelswith", "Rowena", "Edyth"],
        "surnames": ["Blackwood", "Fernsby", "Ashby", "Cromwell", "Dunmore", "Greystone", "Hartwell", "Ironbridge"],
        "pattern": "{given} {surname}",
    },
    "arabic": {
        "given_male": ["Tariq", "Farouk", "Rashid", "Mahmoud", "Khalil", "Amir", "Yusuf", "Bilal"],
        "given_female": ["Layla", "Zara", "Fatima", "Nadia", "Soraya", "Yasmin", "Amira", "Rania"],
        "clan": ["al-Rashid", "ibn Khalil", "al-Aziz", "bint Nour", "al-Hakim"],
        "pattern": "{given} {clan}",
    },
    "slavic": {
        "given_male": ["Dmitri", "Vasil", "Bogdan", "Mirko", "Radovan", "Stanimir", "Vladek"],
        "given_female": ["Natasha", "Svetlana", "Ludmila", "Darya", "Mila", "Vera", "Zora"],
        "surnames": ["Volkov", "Morozov", "Sokolov", "Petrov", "Kozlov", "Lebedev", "Novak"],
        "pattern": "{given} {surname}",
    },
}

# Loot table with named items and descriptions
LOOT_TABLE = [
    # Common
    {"name": "Worn Leather Satchel", "rarity": "common", "type": "container", "desc": "Cracked at the seams but still holds."},
    {"name": "Iron Ration Pack", "rarity": "common", "type": "consumable", "desc": "Hard tack, dried meat, a small flask of oil."},
    {"name": "Tallow Candle Bundle", "rarity": "common", "type": "utility", "desc": "Six short candles wrapped in hemp cord."},
    {"name": "Mending Kit", "rarity": "common", "type": "utility", "desc": "Needle, waxed thread, a patch of boiled leather."},
    {"name": "Road Salt Pouch", "rarity": "common", "type": "trade", "desc": "A draw-string pouch of coarse salt. Every trader wants some."},
    {"name": "Rusted Belt Knife", "rarity": "common", "type": "weapon", "desc": "Chipped edge, worn grip. Cuts rope. Barely."},
    {"name": "Oakwood Walking Staff", "rarity": "common", "type": "weapon", "desc": "Dense grain, good balance, doubles as a prod."},
    {"name": "Sheepskin Bedroll", "rarity": "common", "type": "utility", "desc": "Smells of lanolin. Warm enough for most nights."},
    # Uncommon
    {"name": "Copperhead Blade", "rarity": "uncommon", "type": "weapon", "desc": "Thin, fast. The copper wash hides bloodstains."},
    {"name": "Traveller's Lantern", "rarity": "uncommon", "type": "utility", "desc": "Shuttered iron lantern. The lens bends light in strange angles."},
    {"name": "Physician's Wrap", "rarity": "uncommon", "type": "consumable", "desc": "Clean linen and cedar oil. Stops bleeding when applied firmly."},
    {"name": "Signal Mirror", "rarity": "uncommon", "type": "utility", "desc": "Polished tin disk. Works at half a league on a clear day."},
    {"name": "Weighted Throwing Stars", "rarity": "uncommon", "type": "weapon", "desc": "Four flat iron discs. Painful at range, retrievable after."},
    {"name": "Smoke Herb Bundle", "rarity": "uncommon", "type": "consumable", "desc": "Dried frostbane and thistle. Burns with a thick grey pall."},
    {"name": "Hollow-Toe Boot", "rarity": "uncommon", "type": "wearable", "desc": "The false toe holds a coin, a key, or a single vial."},
    {"name": "Waxseal Kit", "rarity": "uncommon", "type": "utility", "desc": "A brass seal, blank-faced. Marks documents as official-looking."},
    # Rare
    {"name": "Serpent-Scale Vest", "rarity": "rare", "type": "armor", "desc": "River-wyrm scales stitched on boiled hide. Flexible and proof against blades."},
    {"name": "Whisper Ink", "rarity": "rare", "type": "utility", "desc": "Dries invisible. Heat reveals the text. Used by couriers who trust no one."},
    {"name": "Bonewhite Talisman", "rarity": "rare", "type": "accessory", "desc": "Carved from a molar. Warm to the touch. Locals cross themselves when they see it."},
    {"name": "Lodestone Compass", "rarity": "rare", "type": "utility", "desc": "Points to the nearest concentration of iron. Unreliable near mountains."},
    {"name": "Poisoner's Ring", "rarity": "rare", "type": "accessory", "desc": "The hollow bezel unscrews. Whatever you put there tastes of nothing."},
    {"name": "Twin-Bladed Sickle", "rarity": "rare", "type": "weapon", "desc": "A crescent blade on each end. Harvest tool. Killing tool. Same motion."},
    {"name": "Ember Cloak", "rarity": "rare", "type": "armor", "desc": "Treated with rendered salamander fat. Sheds sparks without igniting."},
    {"name": "Apothecary's Chest", "rarity": "rare", "type": "container", "desc": "Twelve labelled vials. Four are poisons. Three are antidotes. One is unlabelled."},
    # Legendary
    {"name": "Moonblind Sword", "rarity": "legendary", "type": "weapon", "desc": "The edge reflects no light. In full dark, the wielder sees its outline like a crack in the world."},
    {"name": "Covenant Seal", "rarity": "legendary", "type": "accessory", "desc": "A wax seal that cannot be forged. Things bound by it stay bound."},
    {"name": "The Long Debt Ledger", "rarity": "legendary", "type": "utility", "desc": "Names everyone who owes you something. Names them accurately. You did not write them there."},
]

# Ability/proficiency registry
ABILITY_REGISTRY = [
    # Combat
    {"name": "Iron Guard", "type": "passive", "domain": "combat", "desc": "You take half damage from the first hit in any engagement."},
    {"name": "Rapid Strike", "type": "active", "domain": "combat", "desc": "Two quick hits instead of one. Each does less damage."},
    {"name": "Disarm", "type": "active", "domain": "combat", "desc": "You strip a weapon from an opponent's grip. Requires a precision roll."},
    {"name": "Killing Calm", "type": "passive", "domain": "combat", "desc": "You do not panic. Bonus to all actions while injured."},
    {"name": "Feint", "type": "active", "domain": "combat", "desc": "Fake an attack direction. Target's next defense roll is halved."},
    # Social
    {"name": "Silver Tongue", "type": "passive", "domain": "social", "desc": "You lie convincingly. Deception rolls have a +2 bonus."},
    {"name": "Reading the Room", "type": "passive", "domain": "social", "desc": "You sense the mood before speaking. +1 to all social rolls in group settings."},
    {"name": "Debt Leverage", "type": "active", "domain": "social", "desc": "When you know someone owes you, remind them. They comply once."},
    {"name": "False Face", "type": "active", "domain": "social", "desc": "Adopt a demeanor that is not yours. Works until closely examined."},
    # Utility
    {"name": "Shadowstep", "type": "active", "domain": "stealth", "desc": "Move silently up to ten metres while in low light."},
    {"name": "Dead Drop", "type": "active", "domain": "stealth", "desc": "Hide a small object where only you can find it again."},
    {"name": "Pick Lock", "type": "active", "domain": "craft", "desc": "Open any standard lock given time and a thin implement."},
    {"name": "Field Stitch", "type": "active", "domain": "medicine", "desc": "Stabilise a wound in the field. Stops bleeding, no healing."},
    {"name": "Track Quarry", "type": "active", "domain": "survival", "desc": "Follow someone who passed through here within the last day."},
    {"name": "Forage", "type": "active", "domain": "survival", "desc": "Find edible plants, clean water, or shelter in the wilderness."},
    # Arcane
    {"name": "Candle Whisper", "type": "active", "domain": "arcane", "desc": "Speak through any open flame within fifty metres."},
    {"name": "Shadow Pup", "type": "active", "domain": "summon", "desc": "Call a small shadow-beast. It obeys one command. It dissolves at dawn."},
    {"name": "Grave Chill", "type": "active", "domain": "necro", "desc": "Drop the temperature in a five-metre radius. Slows; does not freeze."},
    {"name": "Binding Word", "type": "active", "domain": "arcane", "desc": "Speak a word that sticks in someone's memory. They remember it exactly."},
]

# Situation/event seed list for variety
SITUATION_SEEDS = [
    # Social situations
    "A merchant's ledger has gone missing the night before a large payment is due.",
    "Two travellers at the same inn claim to be the same person by different names.",
    "A child follows the player from the market. Will not say why.",
    "A letter addressed to a dead person arrives. Someone expects it to be delivered.",
    "A local official owes a significant debt to an unseen third party. Everyone knows except the official.",
    "A festival is being held but the townspeople seem frightened rather than festive.",
    "A healer refuses to treat a specific patient. Will not explain why.",
    # Conflict situations
    "Two factions dispute ownership of the same well. Both have documentation.",
    "A soldier has deserted and is hiding among the traders. The patrol is three hours behind.",
    "A road toll has doubled overnight with no official explanation.",
    "Someone has been poisoned slowly and is only now realising it.",
    "A prisoner transport is moving through town. The prisoner is asking for help quietly.",
    # Mystery situations
    "Footprints in the mud end in the middle of a field. Nothing else disturbed.",
    "A locked room has been searched from the inside. No one entered or left.",
    "Three travellers passed through last week. None arrived at their destination.",
    "An old contract resurfaces naming the player as heir to something unexpected.",
    "A name carved into a post is the same name the player heard yesterday, in a different town.",
    # Commerce and trade
    "A shipment of grain has arrived short by half. Both parties insist they counted correctly.",
    "A rare material is available cheaply because the seller needs to leave town fast.",
    "An auction is being held for an item whose previous three owners all suffered misfortune.",
    "A guild has declared a competitor's goods counterfeit. The competitor disagrees loudly.",
    # Travel and wilderness
    "A bridge has been sabotaged. Someone wanted traffic stopped.",
    "A campsite has been abandoned mid-meal. The fire is still warm.",
    "A road marker has been turned. Someone changed the direction deliberately.",
    "A wounded animal is being used as bait. Someone is waiting to see who stops.",
]


def naming_context_block() -> str:
    """Compact naming guidance for LLM injection."""
    lines = ["# Naming patterns (pick one cultural register and stay consistent)"]
    for culture, data in NAMING_PATTERNS.items():
        lines.append(f"## {culture.replace('_', ' ').title()}")
        sample_names = []
        for key, vals in data.items():
            if key != "pattern" and isinstance(vals, list):
                sample_names.extend(vals[:3])
        lines.append(", ".join(sample_names[:6]))
    return "\n".join(lines)


def loot_context_block(rarity_filter: str | None = None) -> str:
    """Compact loot table for LLM injection."""
    items = LOOT_TABLE
    if rarity_filter:
        items = [i for i in items if i["rarity"] == rarity_filter]
    lines = ["# Available named items (prefer these over inventing new ones)"]
    for item in items:
        lines.append(f"- {item['name']} ({item['rarity']}): {item['desc']}")
    return "\n".join(lines)


def ability_context_block(domain_filter: str | None = None) -> str:
    """Compact ability registry for LLM injection."""
    abilities = ABILITY_REGISTRY
    if domain_filter:
        abilities = [a for a in abilities if a["domain"] == domain_filter]
    lines = ["# Known abilities (use these codes when granting abilities)"]
    for ab in abilities:
        lines.append(f"- {ab['name']} ({ab['domain']}, {ab['type']}): {ab['desc']}")
    return "\n".join(lines)


def situation_seeds_block(count: int = 3) -> str:
    """Random situation seeds for variety."""
    import random
    seeds = random.sample(SITUATION_SEEDS, min(count, len(SITUATION_SEEDS)))
    lines = ["# Situation seeds (optional inspiration for world events)"]
    for seed in seeds:
        lines.append(f"- {seed}")
    return "\n".join(lines)
