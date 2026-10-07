"""
Example pools: a few fresh examples per call, never the same fixed list.

Fixed example lists in prompts get pasted. Two games in a row opened with
"Aria the baker" because the draft prompt named Aria and a baker on every turn,
and two characters were called "Miriam Shaw" (playtest #14, #21, #26). Taking
examples out entirely made a 7B fall back on its own house names instead. The
fix that holds is the one the user asked for: every call gets three to five
examples drawn at random from a large pool, filtered by the world it is for,
and a name or job already used in this world is never drawn again.

  * ``draw(kind, context, n, rng, exclude)`` returns fresh entries of one kind.
    ``context`` comes from ``world_context()`` (era, magic, naming culture,
    climate, place, settlement size, water, sex, age band). Entries carry
    tags; an entry fits when every tag it carries agrees with what the
    context knows. Unknown context passes.
  * Names: given and family names by naming culture. A name already held by
    an NPC, recorded in ``name_ledger``, or held by the player is excluded,
    and so is any given name already in use, so a world never has two Arias.
    Recent player names are kept in ``player_name_history`` (not part of a
    campaign, never exported) so a new game does not hand back last game's
    character name.
  * Jobs: the occupation pools in ``app/world.py`` (``_SEED_ROLE_POOLS``) by
    era and kind of place, widened here by settlement size, water and magic.
    A net mender is only drawn where there is water.
  * Hard values (eye colour, a notable mark, hair colour and length, the
    colour and wear of the clothes) are rolled by the engine
    (``roll_setup_values``). The model writes the field's prose around them;
    ``apply_rolled_values`` puts back any rolled value the prose dropped.
"""
from __future__ import annotations

import random
import re
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# Entries and filtering
# ---------------------------------------------------------------------------

Entry = tuple[str, dict[str, Any]]

ERAS = ("preindustrial", "industrial", "modern", "future")
PRE = ("preindustrial",)
IND = ("industrial",)
MOD = ("modern",)
FUT = ("future",)
OLD = ("preindustrial", "industrial")
NEW = ("modern", "future")
OPEN_MAGIC = ("common utility", "cultivation")
SOME_MAGIC = ("rare", "common utility", "cultivation", "forbidden")
SMALL = ("wilds", "hamlet", "village")
TOWNISH = ("town", "city")


def _e(text: str, **tags: Any) -> Entry:
    return (text, tags)


def _plain(items: Iterable[str], **tags: Any) -> list[Entry]:
    return [(item, dict(tags)) for item in items]


def _fits(tags: dict[str, Any], ctx: dict[str, Any]) -> bool:
    for key, allowed in tags.items():
        if key == "water":
            # Strict: a water job needs water here, not merely an unknown place.
            if allowed and not ctx.get("water"):
                return False
            continue
        value = ctx.get(key)
        if value in (None, ""):
            continue
        if isinstance(allowed, (tuple, list, set, frozenset)):
            if value not in allowed:
                return False
        elif value != allowed:
            return False
    return True


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


# ---------------------------------------------------------------------------
# Names by naming culture
# ---------------------------------------------------------------------------
# Names a model reaches for unprompted (Aria, Elara, Lyra, Kael, Voss, Thorn)
# are left out on purpose, and so are the old fixed fallback names.

_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "common": {
        "female": (
            "Agnes", "Alys", "Amice", "Annora", "Avelina", "Beatrix", "Bertha", "Brida", "Cecily",
            "Clemence", "Constance", "Dorcas", "Edith", "Edwina", "Ellen", "Elsabet", "Emmot",
            "Ermengarde", "Esme", "Ffion", "Gisela", "Gunilda", "Hawise", "Helewise", "Hilde", "Ida",
            "Idony", "Isolde", "Jehane", "Joan", "Juliana", "Katerine", "Lettice", "Mabel", "Magda",
            "Margery", "Marion", "Matilda", "Maud", "Melisent", "Millicent", "Nesta", "Nichola",
            "Odelia", "Orabel", "Petronel", "Philippa", "Rohese", "Rosamund", "Sabine", "Sarra",
            "Sibyl", "Tamsin", "Ursula", "Wenna", "Wymarc", "Yolande", "Alditha", "Bryony",
            "Cressida", "Delphine", "Eda", "Fenella", "Griselda", "Hester", "Iseult", "Jocosa",
            "Kendra", "Linnet", "Merewyn", "Nell", "Oriel", "Rhoswen", "Sunniva", "Tilda", "Una",
            "Verity", "Winifred", "Gwenllian", "Avice",
        ),
        "male": (
            "Aldous", "Alaric", "Ambrose", "Anselm", "Arnulf", "Baldric", "Bartholomew", "Benedict",
            "Bertram", "Cuthbert", "Dunstan", "Eadric", "Edmund", "Egbert", "Elias", "Emery",
            "Everard", "Fulk", "Gervase", "Giles", "Godfrey", "Gregory", "Hamon", "Hereward",
            "Hubert", "Hugh", "Humphrey", "Ivo", "Jasper", "Jocelin", "Lambert", "Leofric", "Lionel",
            "Mattias", "Milo", "Nicol", "Odo", "Osbert", "Osric", "Payne", "Peregrine", "Piers",
            "Ralf", "Randolph", "Reinald", "Roger", "Rolf", "Sewal", "Simon", "Stephen", "Theobald",
            "Tobin", "Ulric", "Walter", "Warin", "Wystan", "Abel", "Bennet", "Colm", "Dafydd",
            "Emrys", "Finnian", "Gareth", "Hal", "Ingram", "Jory", "Kit", "Lowen", "Madoc", "Ned",
            "Oswin", "Percival", "Quentin", "Rhys", "Silas", "Tam", "Wat", "Wulfstan", "Aubrey",
            "Clement",
        ),
        "family": (
            "Ashby", "Barrow", "Bexley", "Bramley", "Brewster", "Brooke", "Carver", "Chandler",
            "Cobb", "Colley", "Cotter", "Cropper", "Dale", "Draper", "Dunning", "Elwood",
            "Fairweather", "Farrow", "Fenwick", "Fletcher", "Forester", "Fowler", "Furlong", "Gage",
            "Garner", "Gilchrist", "Glover", "Goodwin", "Halloway", "Harrow", "Hatcher", "Hayward",
            "Heddle", "Hollis", "Hooper", "Hurst", "Inchley", "Joliffe", "Kemp", "Kettle", "Lacey",
            "Lambard", "Langley", "Larkin", "Lockwood", "Lowther", "Marlow", "Millward", "Moorcroft",
            "Nash", "Nettles", "Northcott", "Oakes", "Orme", "Padgett", "Penhallow", "Pennick",
            "Pollard", "Quarrel", "Radley", "Redfern", "Ridley", "Rooke", "Rowntree", "Sadler",
            "Sallow", "Saxby", "Shepherd", "Skinner", "Slade", "Stanbury", "Stockwell", "Strand",
            "Tapley", "Thackeray", "Thatcher", "Tolley", "Trask", "Tully", "Underhill", "Vane",
            "Venn", "Wadley", "Wainwright", "Walden", "Warrender", "Webb", "Whitlock", "Wick",
            "Winslow", "Woodall", "Yardley", "Yates", "Abbot", "Bellamy", "Coldwell", "Dunmore",
            "Everly", "Frome", "Grisham", "Hobb", "Ilsley", "Jessop", "Kirkby", "Lightfoot", "Moss",
            "Nayler", "Oldfield", "Prowse", "Rendle", "Sowerby", "Treloar", "Upcott", "Ashdown",
            "Birtle", "Croft", "Dimmock", "Eastlake",
        ),
    },
    "modern": {
        "female": (
            "Ana", "Chiara", "Daniela", "Esther", "Fatima", "Grace", "Hana", "Ines", "Jade", "Kavya",
            "Leah", "Mei", "Olivia", "Priya", "Rosa", "Sofia", "Tanya", "Uma", "Valeria", "Wen",
            "Ximena", "Yasmin", "Zoe", "Abigail", "Bianca", "Camille", "Dana", "Erin", "Farah",
            "Gemma", "Harper", "Imani", "Joanna", "Keiko", "Lucia", "Maya", "Noor", "Paula", "Rachel",
            "Simone", "Teresa", "Vanessa", "Whitney", "Yara", "Alina", "Beth", "Carmen", "Diane",
            "Freya", "Gloria", "Helen", "Irene", "Julia", "Kim", "Laura", "Monique", "Nina", "Opal",
            "Renee", "Sasha", "Tessa", "Vera", "Wanda", "Adaeze", "Bisi", "Chioma", "Dilnoza",
            "Eun-ji", "Marisol", "Ngozi",
        ),
        "male": (
            "Aaron", "Bilal", "Carlos", "Daniel", "Emeka", "Felipe", "Gabriel", "Hassan", "Ivan",
            "Jamal", "Kenji", "Luca", "Nikhil", "Omar", "Pavel", "Quinn", "Rafael", "Samuel", "Tomas",
            "Umar", "Victor", "Wesley", "Xavier", "Yusuf", "Zane", "Andre", "Ben", "Chris", "Dev",
            "Eli", "Frank", "Glen", "Henry", "Isaac", "Joel", "Kofi", "Leon", "Mateo", "Nate",
            "Oscar", "Pete", "Raj", "Sean", "Theo", "Vince", "Will", "Yosef", "Adrian", "Bruno",
            "Caleb", "Dmitri", "Ethan", "Farid", "Gus", "Hiro", "Imran", "Jonah", "Kurt", "Lars",
            "Mohan", "Neil", "Paolo", "Ramon", "Stefan", "Tyrone", "Vikram", "Wyatt", "Zeke",
            "Arjun", "Tunde",
        ),
        "family": (
            "Adebayo", "Alvarez", "Bauer", "Bianchi", "Chen", "Costa", "Dasgupta", "Delgado",
            "Dubois", "Eriksen", "Fischer", "Fontaine", "Garcia", "Gupta", "Haddad", "Hoffmann",
            "Ibrahim", "Ito", "Jansen", "Jovanovic", "Kaur", "Kowalski", "Kim", "Laurent",
            "Lindqvist", "Lopez", "Mbeki", "Mendes", "Moreau", "Nakamura", "Novak", "Nwosu",
            "Okafor", "Olsen", "Ortiz", "Park", "Patel", "Petrov", "Quinlan", "Ramos", "Reyes",
            "Rossi", "Sato", "Schmidt", "Silva", "Singh", "Sokolov", "Tanaka", "Torres", "Tran",
            "Ueda", "Vargas", "Varga", "Volkov", "Walsh", "Weber", "Wong", "Yilmaz", "Zhang",
            "Zielinski", "Abbott", "Barnes", "Carter", "Doyle", "Ellis", "Foster", "Gallagher",
            "Hughes", "Irwin", "Jenkins", "Kelly", "Lambert", "Morgan", "Nolan", "O'Brien", "Parker",
            "Reid", "Sutton", "Turner", "Vaughn", "Ward", "Young", "Brennan", "Castillo", "Duarte",
            "Fernandes", "Gomez", "Herrera", "Iqbal", "Khan", "Larsen", "Molina", "Nguyen", "Osei",
            "Pereira", "Rahman", "Santos", "Tiwari", "Vu", "Watanabe",
        ),
    },
    "norse": {
        "female": (
            "Astrid", "Bergljot", "Dagny", "Eydis", "Freydis", "Gudrun", "Gunnhild", "Halla", "Helga",
            "Hildr", "Ingrid", "Jorunn", "Katla", "Liv", "Ragna", "Ragnhild", "Signy", "Sigrid",
            "Solveig", "Svala", "Thora", "Thordis", "Tove", "Unn", "Vigdis", "Yrsa", "Aud", "Bodil",
            "Embla", "Frida", "Asa", "Geirny", "Hallveig", "Oddny",
        ),
        "male": (
            "Arne", "Bjorn", "Dag", "Egil", "Einar", "Erling", "Finnbogi", "Geir", "Gisli", "Grim",
            "Gunnar", "Hakon", "Halfdan", "Hrafn", "Ivar", "Kari", "Ketil", "Leif", "Njal", "Odd",
            "Orm", "Ragnar", "Sigurd", "Snorri", "Steinar", "Sven", "Thorvald", "Ulf", "Vali",
            "Yngvar", "Asgeir", "Bersi", "Eyvind", "Hallbjorn",
        ),
        # Patronymics are built from the male names (see _family_names).
        "family": (),
    },
    "latin": {
        "female": (
            "Aelia", "Antonia", "Aurelia", "Caecilia", "Camilla", "Claudia", "Cornelia", "Domitia",
            "Fabia", "Flavia", "Junia", "Livia", "Lucilla", "Marcia", "Octavia", "Paulina",
            "Plautia", "Porcia", "Sabina", "Servilia", "Sulpicia", "Tertia", "Tullia", "Vipsania",
            "Agrippina", "Calpurnia", "Drusilla", "Fulvia", "Galeria", "Hortensia",
        ),
        "male": (
            "Aulus", "Caius", "Decimus", "Gnaeus", "Lucius", "Numerius", "Publius", "Quintus",
            "Servius", "Sextus", "Spurius", "Tiberius", "Titus", "Appius", "Cassius", "Cato",
            "Crispus", "Felix", "Gallus", "Lepidus", "Marius", "Nerva", "Otho", "Priscus", "Rufus",
            "Severus", "Silvanus", "Varro", "Vitus", "Manius",
        ),
        "family": (
            "Aemilius", "Antonius", "Aurelius", "Caecilius", "Calpurnius", "Claudius", "Cornelius",
            "Domitius", "Fabius", "Flavius", "Fulvius", "Junius", "Licinius", "Livius", "Marcius",
            "Octavius", "Petronius", "Pompeius", "Porcius", "Quinctius", "Sempronius", "Sergius",
            "Servilius", "Sulpicius", "Terentius", "Tullius", "Valerius", "Vettius", "Vipsanius",
            "Annius", "Betilienus", "Coelius",
        ),
    },
    "slavic": {
        "female": (
            "Agnieszka", "Bozena", "Danica", "Dragana", "Galina", "Halina", "Irina", "Jadwiga",
            "Katya", "Lada", "Ludmila", "Marta", "Milena", "Nadezhda", "Olena", "Radka", "Svetlana",
            "Tatiana", "Vesna", "Yelena", "Zofia", "Zora", "Bogna", "Dobrava", "Jelena", "Libuse",
            "Mirka", "Snezana", "Vlasta", "Zlata",
        ),
        "male": (
            "Bogdan", "Borislav", "Branko", "Dobromir", "Dusan", "Goran", "Igor", "Jaromir",
            "Kazimir", "Lech", "Milos", "Miroslav", "Nikola", "Oleg", "Radomir", "Ratimir", "Slavko",
            "Stanislav", "Svyatoslav", "Vadim", "Vlad", "Vojtech", "Yaroslav", "Zbigniew", "Zdenek",
            "Ziven", "Tomislav", "Bozidar", "Wojciech", "Mstislav",
        ),
        "family": (
            "Babic", "Bartos", "Dvorak", "Horvat", "Jankovic", "Kovac", "Kral", "Kucera", "Lisowski",
            "Marek", "Mazur", "Nemec", "Novotny", "Orlov", "Pavlic", "Petrovic", "Polak", "Rybak",
            "Sadowski", "Simic", "Sokol", "Svoboda", "Tkach", "Urban", "Vesely", "Wolski", "Zajac",
            "Zelenko", "Zoric", "Hrabal",
        ),
    },
    "arabic": {
        "female": (
            "Amira", "Aziza", "Dalia", "Farida", "Ghada", "Habiba", "Hayat", "Jamila", "Karima",
            "Laila", "Lubna", "Maha", "Malika", "Nadira", "Nasrin", "Parisa", "Rana", "Rasha",
            "Salma", "Samira", "Shirin", "Soraya", "Zahra", "Zainab", "Zarina", "Afsaneh", "Bahar",
            "Golnar", "Roxana", "Thurayya",
        ),
        "male": (
            "Amir", "Bashir", "Dariush", "Faris", "Farhad", "Hakim", "Hamid", "Idris", "Jafar",
            "Kamal", "Karim", "Khalid", "Mansur", "Nasir", "Rashid", "Rostam", "Saad", "Salim",
            "Tariq", "Yazid", "Zayd", "Ardeshir", "Bahram", "Cyrus", "Kaveh", "Mehran", "Navid",
            "Parviz", "Sohrab", "Usama",
        ),
        "family": (
            "Abbasi", "Ansari", "Attar", "Bakri", "Darwish", "Farahani", "Ghazali", "Hashemi",
            "Jaber", "Kazemi", "Khalili", "Mansouri", "Masri", "Nadir", "Najjar", "Qasimi", "Rahimi",
            "Sabbagh", "Saffar", "Shirazi", "Tabrizi", "Yazdi", "Zand", "Asadi", "Behzadi",
            "Daneshvar", "Esfahani", "Golzar", "Mirza", "Kassab",
        ),
    },
    "japanese": {
        "female": (
            "Akane", "Aoi", "Chiyo", "Emi", "Fumiko", "Haruka", "Hikari", "Kaede", "Kiku", "Kotone",
            "Mai", "Midori", "Mitsuki", "Nanami", "Natsu", "Noriko", "Rin", "Sayuri", "Setsuko",
            "Shizuka", "Suzu", "Tomoe", "Ume", "Yae", "Yoshino", "Yuna", "Asami", "Kasumi", "Michiru",
            "Sachi",
        ),
        "male": (
            "Akira", "Daisuke", "Eiji", "Goro", "Haruto", "Hideo", "Isamu", "Jiro", "Kaito", "Kazuo",
            "Kenta", "Kiyoshi", "Makoto", "Masaru", "Minoru", "Noboru", "Osamu", "Ryota", "Saburo",
            "Shiro", "Shota", "Takeshi", "Tatsuya", "Tetsu", "Yasuo", "Yoshiro", "Yuji", "Sota",
            "Hayato", "Kosuke",
        ),
        "family": (
            "Aoki", "Endo", "Fujita", "Fukuda", "Hasegawa", "Hayashi", "Ikeda", "Inoue", "Ishikawa",
            "Kato", "Kimura", "Kobayashi", "Kondo", "Maeda", "Matsuda", "Mori", "Murakami", "Nakano",
            "Nishida", "Ogawa", "Okada", "Saito", "Sakamoto", "Shimizu", "Suzuki", "Takahashi",
            "Tamura", "Ueno", "Yamada", "Yoshida",
        ),
    },
    "chinese": {
        "female": (
            "Ai", "Bao", "Chun", "Fang", "Hua", "Hui", "Jia", "Jing", "Lan", "Lian", "Ling", "Mei",
            "Min", "Ning", "Ping", "Qing", "Rou", "Shu", "Ting", "Wan", "Xia", "Xiu", "Yan", "Yi",
            "Ying", "Yu", "Yun", "Zhen", "Zhi", "Xiaolan",
        ),
        "male": (
            "Bo", "Cheng", "Da", "Gang", "Hao", "Heng", "Hong", "Jian", "Jun", "Kai", "Lei", "Long",
            "Ming", "Peng", "Qiang", "Rui", "Shan", "Tao", "Wei", "Wen", "Xiang", "Xin", "Yang",
            "Yong", "Zhuo", "Zhong", "Ze", "Kang", "Yifan", "Zihan",
        ),
        "family": (
            "Bai", "Cao", "Chen", "Deng", "Du", "Fang", "Feng", "Gao", "Guo", "Han", "He", "Hu",
            "Huang", "Jiang", "Li", "Liang", "Lin", "Liu", "Lu", "Ma", "Pan", "Qin", "Shen", "Song",
            "Su", "Tang", "Wang", "Wu", "Xu", "Ye", "Zhao", "Zhou", "Zhu",
        ),
    },
}

# Family name first, as the culture writes it.
_FAMILY_FIRST = {"chinese"}

# Keywords that pick a naming culture out of the world's own words. Ordered:
# the first culture with a hit wins. No hit: "modern" for modern and future
# worlds, "common" otherwise.
_CULTURE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chinese", ("xianxia", "wuxia", "jianghu", "cultivation", "immortal sect", "qi ", "dynasty", "chinese", "jade emperor")),
    ("japanese", ("samurai", "shogun", "ronin", "japan", "japanese", "edo", "yokai", "shinto", "daimyo")),
    ("norse", ("viking", "norse", "fjord", "jarl", "saga", "skald", "longship", "valhalla")),
    ("latin", ("roman", "legion", "imperium", "senate", "latin", "praetor", "centurion")),
    ("slavic", ("slavic", "boyar", "tsar", "kievan", "rus ", "voivode", "baba yaga")),
    ("arabic", ("sultan", "caliph", "djinn", "jinn", "caravanserai", "bazaar", "oasis", "emirate", "vizier", "persian")),
)


def detect_culture(text: str, era: str = "") -> str:
    blob = f" {_norm(text)} "
    for culture, words in _CULTURE_HINTS:
        if any(word in blob for word in words):
            return culture
    return "modern" if era in NEW else "common"


def _given_names(culture: str, sex: str) -> list[str]:
    table = _NAMES.get(culture) or _NAMES["common"]
    if sex in ("female", "male"):
        return list(table[sex])
    # Sex open: both lists, interleaved so a short draw is mixed.
    out: list[str] = []
    for a, b in zip(table["female"], table["male"]):
        out += [a, b]
    return out


def _family_names(culture: str, sex: str) -> list[str]:
    table = _NAMES.get(culture) or _NAMES["common"]
    if culture == "norse":
        suffix = "sdottir" if sex == "female" else "sson"
        return [f"{name}{suffix}" if not name.endswith("s") else f"{name}{suffix[1:]}" for name in table["male"]]
    family = list(table["family"])
    if culture == "latin" and sex == "female":
        family = [re.sub(r"ius$", "ia", name) for name in family]
    return family


def _render_name(culture: str, given: str, family: str) -> str:
    if not family:
        return given
    return f"{family} {given}" if culture in _FAMILY_FIRST else f"{given} {family}"


_ROSTER_PARTS: frozenset[str] | None = None


def is_roster_name_part(word: str) -> bool:
    """True when ``word``, exactly as written, is a given or family name in the pools.

    Live gate N1: "Li Ping", drawn from these pools for cast_options, failed the
    person-name check because "Ping" reads as the verb "pings", and the name
    repair renamed the merchant in the prose. The engine's own roster is
    the answer to "is this a name".
    """
    global _ROSTER_PARTS
    if _ROSTER_PARTS is None:
        _ROSTER_PARTS = frozenset(
            part for pools in _NAMES.values() for names in pools.values() for part in names
        )
    return str(word or "") in _ROSTER_PARTS


def _name_tokens(name: str) -> set[str]:
    return {part for part in re.split(r"[\s\-']+", _norm(name)) if len(part) >= 2}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
# Widening of app/world.py _SEED_ROLE_POOLS (which stay the base pools). Each
# entry carries the kind of place it belongs to and, where it matters, the
# settlement sizes, water, or magic it needs.

_ROLE_EXTRAS: list[Entry] = [
    # --- preindustrial, settled
    *_plain((
        "potter", "thatcher", "rope maker", "candle maker", "basket weaver", "dyer", "fuller",
        "miller", "brewer", "alewife", "midwife", "bonesetter", "barber", "tinker", "knife grinder",
        "rat catcher", "gravedigger", "bell ringer", "sexton", "bailiff", "furrier", "saddler",
        "wheelwright", "smith's striker", "farrier", "locksmith", "cobbler", "laundress",
        "seamstress", "cheesemaker", "butcher", "grocer", "pie seller", "water carrier",
        "woodseller", "ostler", "stable lad", "mason", "carpenter", "plasterer", "shingler",
        "tallow chandler", "wet nurse", "hedge schoolteacher", "rag seller", "egg seller",
    ), era=PRE, place=("settlement",)),
    *_plain((
        "moneychanger", "pawnbroker", "bookbinder", "illuminator", "glassblower", "goldsmith",
        "jeweller", "lamplighter", "hatter", "town crier", "notary", "spice seller", "wine merchant",
        "physician", "parchment maker", "dancing master", "fencing teacher", "street sweeper",
        "sedan bearer", "cutpurse's lookout", "guild clerk",
    ), era=PRE, place=("settlement",), size=TOWNISH),
    *_plain((
        "goose herd", "shepherd", "swineherd", "ploughman", "hedger", "thresher", "dairy hand",
        "hayward", "mole catcher", "woodward", "beekeeper", "orchard keeper", "reed cutter",
        "village reeve", "smallholder", "gleaner",
    ), era=PRE, place=("settlement", "wilderness"), size=SMALL),
    *_plain((
        "fishmonger", "sailmaker", "caulker", "lighterman", "rope walker", "harbour pilot",
        "shipwright", "boat builder", "eel trapper", "fish smoker", "wherryman", "oyster seller",
        "fish gutter", "lock keeper", "crab potter", "tide watcher",
    ), era=PRE, place=("water", "settlement"), water=True),
    *_plain((
        "pot washer", "cellarman", "chamber servant", "fiddler", "storyteller", "dice player",
        "tapster", "travelling tinker", "drover at rest", "night porter", "hearth sweeper",
    ), era=PRE, place=("indoor",)),
    *_plain((
        "hunter", "falconer", "herb gatherer", "mushroom picker", "quarryman", "miner",
        "lime burner", "pitch boiler", "bark stripper", "wandering friar", "trail guide",
        "shepherd", "honey hunter", "snare setter", "stone cutter", "salt panner",
    ), era=PRE, place=("wilderness",)),
    *_plain((
        "hedge witch", "charm seller", "rune carver", "scryer", "alchemist's runner",
        "ward painter", "potion seller", "familiar keeper",
    ), era=OLD, magic=("common utility", "rare"), place=("settlement", "indoor")),
    *_plain((
        "sect disciple", "pill refiner", "talisman scribe", "spirit herb farmer",
        "array keeper", "outer court servant", "beast tamer",
    ), magic=("cultivation",)),
    # --- industrial
    *_plain((
        "lamplighter", "chimney sweep", "match seller", "newspaper seller", "factory hand",
        "mill worker", "foundry worker", "clerk", "bookkeeper", "pharmacist", "photographer",
        "schoolteacher", "barber", "tailor", "shoe shiner", "cabman", "omnibus driver", "postman",
        "police constable", "engine driver", "stoker", "boilermaker", "gasworks hand",
        "watchmaker", "pawnbroker", "milliner", "laundress", "coal merchant", "rag-and-bone man",
        "organ grinder", "sawmill hand", "blacksmith", "saloon keeper", "stagecoach guard",
        "typesetter", "dressmaker", "nurse", "street preacher", "brewery drayman",
    ), era=IND, place=("settlement",)),
    *_plain((
        "bargee", "ship's chandler", "harbour pilot", "shipwright", "oysterman", "lighterman",
        "customs officer", "lock keeper", "fish porter", "net mender",
    ), era=IND, place=("water", "settlement"), water=True),
    *_plain((
        "miner", "railway navvy", "cowhand", "sheepherder", "logger", "well digger", "trapper",
        "survey chainman", "mule skinner", "camp cook",
    ), era=IND, place=("wilderness",)),
    *_plain((
        "pianist", "card sharp", "chambermaid", "bootblack", "hotel porter", "waiter",
    ), era=IND, place=("indoor",)),
    # --- modern
    *_plain((
        "nurse", "teacher", "pharmacist", "bus driver", "electrician", "plumber", "janitor",
        "hairdresser", "tattoo artist", "bartender", "bouncer", "pawn shop clerk", "food truck cook",
        "social worker", "bike courier", "tow truck driver", "locksmith", "vet tech", "florist",
        "baker", "butcher", "mail carrier", "garbage collector", "construction worker",
        "crossing guard", "librarian", "accountant", "receptionist", "help desk tech",
        "translator", "tailor", "dog walker", "street musician", "journalist", "photographer",
        "firefighter", "convenience store clerk", "laundromat attendant", "parking attendant",
    ), era=MOD, place=("settlement",)),
    *_plain((
        "fish market worker", "ferry pilot", "marina attendant", "lifeguard", "boat rental clerk",
        "fisher", "container yard driver",
    ), era=MOD, place=("water", "settlement"), water=True),
    *_plain((
        "park ranger", "logger", "farmhand", "truck stop clerk", "gas station attendant",
        "forestry worker", "search-and-rescue volunteer", "pipeline inspector", "beekeeper",
    ), era=MOD, place=("wilderness",)),
    *_plain((
        "dishwasher", "host", "bar regular", "karaoke host", "motel clerk", "sous chef",
    ), era=MOD, place=("indoor",)),
    # --- future
    *_plain((
        "hydroponics tech", "drone mechanic", "atmosphere tech", "water reclaimer", "noodle vendor",
        "fabricator operator", "cargo broker", "rigger", "med-bay orderly", "shuttle pilot",
        "airlock warden", "signal tech", "ration clerk", "lift operator", "info broker",
        "bounty clerk", "suit fitter", "nav clerk", "algae farmer", "solar array cleaner",
        "duct crawler", "street doc", "chop-shop mechanic", "hab janitor", "archive tech",
    ), era=FUT, place=("settlement",)),
    *_plain((
        "crane rigger", "berth master", "fuel line tech", "hull scraper", "cargo drone wrangler",
    ), era=FUT, place=("water",), water=True),
    *_plain((
        "ice miner", "rover driver", "beacon tech", "wreck diver", "terraform surveyor",
    ), era=FUT, place=("wilderness",)),
    *_plain((
        "bar synth tech", "bunk steward", "game host", "ration cook",
    ), era=FUT, place=("indoor",)),
]

# Base-pool roles that need water to make sense.
_WATER_ROLE_WORDS = (
    "ferry", "net mender", "boat", "dock", "barge", "mudlark", "eel", "harbo", "riverboat",
    "stevedore", "crane", "tug", "deckhand", "port ", "salt carrier", "coal heaver",
)


def _base_roles(era: str, place: str) -> list[Entry]:
    try:
        from app.world import _SEED_ROLE_POOLS

        pool = _SEED_ROLE_POOLS.get(era or "preindustrial", _SEED_ROLE_POOLS["preindustrial"])
        roles = pool.get(place or "settlement") or pool["settlement"]
    except Exception:
        roles = ()
    out: list[Entry] = []
    for role in roles:
        tags: dict[str, Any] = {}
        if place == "water" or any(word in role for word in _WATER_ROLE_WORDS):
            tags["water"] = True
        out.append((role, tags))
    return out


# ---------------------------------------------------------------------------
# Venue name forms
# ---------------------------------------------------------------------------

_VENUE_ADJ = {
    "old": (
        "Crooked", "Gilded", "Sleeping", "Drowned", "Laughing", "Silver", "Broken", "Red", "Black",
        "Lame", "Patient", "Hungry", "Painted", "Wandering", "Seventh", "Leaning", "Merry", "Grey",
        "Copper", "Twice-Blessed", "Lucky", "Stubborn", "Blind", "Velvet", "Thirsty", "Honest",
    ),
    "new": (
        "Neon", "Lucky", "Midnight", "Second", "Blue", "Static", "Corner", "Golden", "Twelfth",
        "Quiet", "Late", "Rusty", "Open", "Little", "Northside", "Halfway", "Chrome", "Paper",
        "Daily", "Bright",
    ),
}
_VENUE_NOUN = {
    "old": (
        "Lantern", "Anchor", "Stag", "Kettle", "Hound", "Plough", "Goose", "Bell", "Wheel",
        "Ferret", "Crown", "Barrel", "Heron", "Thimble", "Ox", "Ladle", "Badger", "Candle",
        "Pike", "Wren", "Boar", "Spindle", "Mitre", "Shears", "Owl", "Fiddle", "Mermaid", "Key",
        "Pear", "Hare",
    ),
    "new": (
        "Spoon", "Socket", "Comet", "Ticket", "Circuit", "Kettle", "Lantern", "Signal", "Dial",
        "Cassette", "Orbit", "Cactus", "Magnet", "Pixel", "Wrench", "Moth", "Satellite",
        "Thermos", "Tin", "Atlas",
    ),
}
_VENUE_TRADE = {
    "preindustrial": ("Bakehouse", "Forge", "Apothecary", "Provisions", "Stables", "Tannery", "Smithy", "Chandlery", "Cookshop", "Inn", "Tavern", "Mill"),
    "industrial": ("Bakery", "Ironworks", "Dispensary", "Dry Goods", "Livery", "Hotel", "Saloon", "Outfitters", "Pharmacy", "Mercantile"),
    "modern": ("Diner", "Deli", "Pharmacy", "Hardware", "Laundromat", "Garage", "Cafe", "Bar", "Mart", "Repairs"),
    "future": ("Noodle Bar", "Fab Shop", "Clinic", "Salvage", "Parts", "Exchange", "Bunkhouse", "Canteen", "Repair Bay", "Supply"),
}
_VENUE_FORMS: list[Entry] = [
    _e("The {adj} {noun}", era=OLD),
    _e("The {noun} and {noun2}", era=OLD),
    _e("{family}'s {trade}"),
    _e("{family} and Daughters", era=OLD),
    _e("{family} and Sons", era=OLD),
    _e("The {noun}'s Rest", era=OLD),
    _e("{adj} {noun} {trade}"),
    _e("The {adj} {noun}", era=NEW),
    _e("{family} {trade}", era=NEW),
    _e("{noun} {trade}", era=NEW),
    _e("The {noun} at {place}", era=OLD),
    _e("{place} {trade}"),
    # Town grid (docs/TownGrid.md 3.4): the full street name, drawn only when
    # the context carries ``street_name``. "{place}" keeps its one-word form.
    _e("{street} {trade}"),
]

# Town grid: a plot's own trade words by era. A word not listed fits every era.
# The kind words in venues._KIND_WORDS carry no era, so a preindustrial
# bakery could otherwise be drawn as a "Cafe" or an inn as a "Motel".
_TRADE_WORD_ERAS: dict[str, tuple[str, ...]] = {
    "hotel": ("industrial", "modern", "future"),
    "motel": NEW,
    "hostel": ("industrial", "modern", "future"),
    "bunkhouse": ("industrial", "modern", "future"),
    "roadhouse": ("industrial", "modern"),
    "pub": ("industrial", "modern"),
    "beerhall": ("industrial", "modern"),
    "chemist": ("industrial", "modern"),
    "hardware": ("industrial", "modern", "future"),
    "mart": NEW,
    "convenience store": NEW,
    "corner store": ("industrial", "modern"),
    "bodega": NEW,
    "supply": ("industrial", "modern", "future"),
    "supplies": ("industrial", "modern", "future"),
    "outfitters": ("industrial", "modern"),
    "mercantile": ("industrial",),
    "dry goods": ("industrial",),
    "cafe": ("industrial", "modern", "future"),
    "deli": NEW,
    "coffee shop": NEW,
    "restaurant": ("industrial", "modern", "future"),
    "bistro": ("industrial", "modern"),
    "cafeteria": NEW,
    "noodle bar": NEW,
    "noodle shop": NEW,
    "noodle stand": NEW,
    "cookshop": OLD,
    "hospital": ("industrial", "modern", "future"),
    "med bay": FUT,
    "medbay": FUT,
    "medical bay": FUT,
    "sickbay": FUT,
    "sick bay": FUT,
    "med center": NEW,
    "medcenter": FUT,
    "nightclub": NEW,
    "lounge": NEW,
    "saloon": ("industrial",),
    "speakeasy": ("industrial", "modern"),
    "bank": ("industrial", "modern", "future"),
    "fab shop": FUT,
    "repair bay": FUT,
    "auto shop": MOD,
    "body shop": MOD,
    "chop shop": NEW,
    "motor works": ("industrial", "modern"),
    "pump": ("industrial", "modern", "future"),
    "archive": ("preindustrial", "industrial", "modern", "future"),
}
# Forms with no {trade} are signs ("The Crooked Lantern"). Only these kinds
# may wear one: classification ignores sign names, so any other plot named
# that way would read as no venue at all.
SIGN_FORM_KINDS = frozenset({"inn", "tavern", "bar"})

_STREET_TAIL = {
    "old": ("Street", "Lane", "Row", "Way", "Road", "Alley", "Court", "Walk"),
    "new": ("Street", "Avenue", "Road", "Drive", "Boulevard", "Lane", "Place", "Way"),
}
_STREET_FORMS: list[Entry] = [
    _e("{noun} {tail}"),
    _e("{adj} {tail}"),
    _e("{family} {tail}"),
    _e("{adj} {noun} {tail}"),
    _e("{noun}gate {tail}", era=OLD),
    _e("Old {noun} {tail}"),
]


# ---------------------------------------------------------------------------
# Setup field phrases
# ---------------------------------------------------------------------------

_PHRASES: dict[str, list[Entry]] = {
    "economy": [
        *_plain((
            "scarce coin, plenty of barter", "debt and credit on a handshake",
            "a few rich houses own most stock", "black markets fill every shortage", "everything costs a favour",
            "hoarding and rationing", "fair prices, thin margins", "smuggling props up the legal trade",
            "one big lender holds everyone's notes", "barter between isolated settlements",
            "cheap food, dear tools", "credit runs out before winter does",
            "local tokens that are worthless next town over", "outsiders pay double",
            "everyone owes the same family",
        )),
        *_plain((
            "coin-driven market days", "tithes skim every sale", "prices swing with the harvest",
            "trade follows the seasons", "wages paid in kind as often as in coin", "tolls on every road",
            "guild-fixed prices", "chronic shortage of good metal", "a market that only runs on feast days",
            "prices rise the further you go from the river",
        ), era=OLD),
        *_plain((
            "copper for bread, silver for land", "lords take a cut of every harvest",
            "caravans set the price of iron", "temple granaries carry bad years",
            "craft guilds decide who may sell", "salt and grain used as money",
        ), era=PRE),
        *_plain((
            "company scrip in the mill towns", "railway freight decides who prospers",
            "banks foreclose after bad seasons", "piece wages and pawnshops", "boom and bust around the mines",
        ), era=IND),
        *_plain((
            "gig work and late rent", "cash jobs under the table", "rationed fuel and ration cards",
            "chain stores and street trade", "salvage traded by weight",
        ), era=MOD),
        *_plain((
            "station credits and ration chits", "water and air priced by the litre",
            "salvage claims traded like stock", "corporate scrip in the habs", "data traded as currency",
        ), era=FUT),
        *_plain((
            "harbour trade sets every price", "fish, salt and rope as the real currency",
            "dock markets that shift with the tide", "ships bring coin, storms take it",
            "customs duty on every crate",
        ), water=True),
        *_plain(("spell components priced like spices", "enchanted goods taxed hard"), magic=("common utility",)),
        *_plain(("spirit stones as coin", "sect contribution points buy everything"), magic=("cultivation",)),
    ],
    "quest_style": [
        *_plain((
            "emergent local work", "job boards and personal mysteries", "faction errands with side mysteries",
            "neighbours' requests that grow complicated", "rumours you choose to chase",
            "contracts posted at the guild", "debts that come due as jobs",
            "one long mystery with local detours", "patrons who pay for discretion",
            "bounties and missing persons", "hauling jobs that go wrong", "favours traded for favours",
            "petitions to whoever holds power", "small jobs tied to a larger conspiracy",
            "exploring past the edge of the map", "investigations that start with a body",
            "escort work on dangerous roads", "repair and salvage contracts",
            "family obligations that pull you in", "trouble that finds you on the road",
            "rival crews racing for the same prize", "the player's own goals, pushed by local pressure",
            "slow-burn feuds you can take a side in", "odd jobs that reveal the town's secrets",
            "requests from strangers who know your name",
        )),
        *_plain((
            "season-bound work: harvests, migrations, storms", "letters that arrive with requests",
            "word-of-mouth jobs from taverns",
        ), era=OLD),
        *_plain(("contract board on the station ring", "salvage claims and data jobs"), era=FUT),
        *_plain(("jobs from a fixer's phone", "case files and leads"), era=MOD),
        *_plain(("newspaper notices and private commissions", "railway and mining company jobs"), era=IND),
        *_plain(("sect missions ranked by difficulty", "trials set by the elders"), magic=("cultivation",)),
        *_plain(("ship charters and cargo runs", "harbour rumours of lost ships"), water=True),
    ],
    "faction_pressure": [
        *_plain((
            "local disputes", "rival families feuding over land", "a militia nobody elected",
            "merchant houses buying loyalty", "a secret society on the town council",
            "refugees and the people who resent them", "old clans against new money",
            "a cult recruiting the desperate", "a debt-holder calling in every loan",
            "outsiders buying up the land",
        )),
        *_plain((
            "guild control of trade", "a lord squeezing tenants", "a temple that taxes the faithful",
            "bandit gangs running the roads", "tax collectors from the capital", "border garrisons on edge",
            "smugglers paying off the watch", "a mine owner who owns the town", "the miller's monopoly",
            "two heirs splitting the province", "the watch and the thieves sharing a payroll",
        ), era=OLD),
        *_plain(("an inquisition hunting heresy", "witch-finders on the roads"), magic=("forbidden",)),
        *_plain(("mage colleges guarding their secrets", "licensed casters against hedge mages"), magic=("common utility",)),
        *_plain(("rival sects competing for disciples", "an elder's feud dragging in outer disciples"), magic=("cultivation",)),
        *_plain(("union organisers against company men", "railway barons and squatters"), era=IND),
        *_plain(("corporate security and street gangs", "city hall and the developers"), era=MOD),
        *_plain((
            "a landlord cartel squeezing every block", "a private militia selling protection",
            "a tech company that owns the water", "rival crews dividing the streets",
        ), era=NEW),
        *_plain((
            "station council against the dock crews", "corporate charters and free haulers",
            "an AI-run administration nobody can appeal", "habitat unions against the owners",
        ), era=FUT),
        *_plain(("pirate crews on the shipping lanes", "harbour masters taking bribes"), water=True),
    ],
    "npc_density": [
        *_plain((
            "sparse", "moderate", "dense", "sparse, busy on market days", "crowded towns, empty roads",
            "thin, wary settlements", "busy streets, quiet nights", "dense with faction patrols",
            "lonely countryside", "seasonal crowds", "a few regulars everywhere",
            "packed around the centre, empty at the edges", "lively but small", "busy by day, deserted by night",
        )),
        *_plain(("packed tenements", "crowded platforms and quiet suburbs"), era=("industrial", "modern")),
        *_plain(("corridors that are never empty", "busy docking rings, empty outer decks"), era=FUT),
        _e("crowded docks", water=True),
    ],
    "npc_stat_scaling": _plain((
        "relative ranks", "mostly weaker", "near player", "elite-heavy later",
        "mostly ordinary, a few dangerous veterans", "scaled to the region", "stronger near cities",
        "weaker locals, stronger outsiders", "a steep gap between commoners and trained fighters",
        "rank follows reputation", "veterans in every garrison", "most weaker, some far stronger",
        "roughly even with the player", "dangerous elites at the top of each faction",
        "strength rises with distance from home", "ordinary people, rare monsters",
    )),
    "npc_skill_frequency": _plain((
        "some trained NPCs", "rare specialists", "occasional trainers", "most adults have one trade skill",
        "specialists only in cities", "skilled people are known by name", "common in guilds, rare elsewhere",
        "a few masters per region", "many dabblers, few experts", "trained guards, untrained everyone else",
        "elders hold the rare skills", "skills passed down within families", "teachers are hard to find",
    )),
    "skill_style": _plain((
        "standard", "training-heavy", "generous discovery with practice", "strict: teachers required",
        "learn by doing", "slow and earned", "mentor-gated", "practice plus rare breakthroughs",
        "use-based growth", "books and drills", "risk speeds learning", "apprenticeship first",
    )),
    "rank_scale": _plain((
        "F,E,D,C,B,A,S,SS,SSS", "D,C,B,A,S", "E,D,C,B,A,S", "G,F,E,D,C,B,A,S", "F,E,D,C,B,A,S",
        "E,D,C,B,A,S,SS", "D,C,B,A,S,SS,SSS", "F,E,D,C,B,A",
    )),
    "world_races": [
        _e("human"),
        *_plain((
            "human, elf, dwarf", "human, riverfolk, beastfolk", "human, halfling", "human, orc, goblin",
            "human, giantkin", "human, fae-touched", "human, lizardfolk", "human, dwarf, gnome",
            "human, catfolk, wolfkin", "human, ogre", "human, treefolk", "human, half-elf",
            "human, kobold", "human, serpentfolk", "human, stoneborn", "human, ashborn",
            "human, gnome, halfling", "human, hill dwarf, wood elf", "human, minotaur", "human, harpy",
        ), era=OLD, magic=SOME_MAGIC),
        *_plain(("human, merfolk", "human, tidekin", "human, sealfolk"), era=OLD, magic=SOME_MAGIC, water=True),
        *_plain(("human, fox spirits", "human, dragon-blooded", "human, demon-blooded", "human, spirit beasts"),
                magic=("cultivation",)),
        *_plain(("human, hidden fae", "human, vampires in hiding", "human, shapeshifters"), era=MOD, magic=SOME_MAGIC),
        *_plain((
            "human, android", "human, uplifted animals", "human, clones", "human, gene-adapted spacers",
            "human, synthetic minds", "human, insectoid traders", "human, void-born",
        ), era=FUT),
    ],
    "player_sex": _plain(("female", "male", "")),
    "previous_life_sex": _plain(("female", "male", "")),
}

# Race rule phrases. Rendered against the world's own peoples, so an example
# names this world's races and nobody else's.
_RACE_MAGIC_RULES = (
    "{race} need formal training to cast", "{race} are born with a small gift that needs practice",
    "{race} cannot cast but resist spells", "{race} cast only through bargains with spirits",
    "{race} sense magic but rarely use it", "{race} work magic through crafts, not spells",
    "{race} cast in groups, never alone", "{race} lose the gift if they leave home",
    "{race} draw power from the land they stand on", "{race} are mostly barred from casting by law",
    "{race} learn from written texts only", "{race} gain magic only after a rite of passage",
    "{race} inherit one minor charm in each family", "{race} cast through song or chant",
    "{race} pay for every spell with fatigue", "{race} have no magic at all",
)
_RACE_ABILITY_RULES = (
    "{race} learn broadly through practice", "{race} see well in the dark", "{race} sense weather changes",
    "{race} tire slowly on long marches", "{race} resist poison and sickness", "{race} hear unusually well",
    "{race} heal a little faster", "{race} climb easily", "{race} hold their breath a long time",
    "{race} remember faces and voices exactly", "{race} feel the old growth of forests",
    "{race} track by scent", "{race} endure cold well", "{race} endure heat well",
    "{race} work stone and metal by touch", "{race} start with no innate gifts",
)

# ---------------------------------------------------------------------------
# World facts (playtest #23): race traits and the kinds of lore to ask for
# ---------------------------------------------------------------------------

# Short traits for a people, so a race row is never empty-traited when no model
# pass runs. A people is matched by a word in its name; anything else draws
# from the general pool. Rolled per world from the campaign seed.
_RACE_TRAITS_BY_WORD: dict[str, tuple[str, ...]] = {
    "human": (
        "short-lived and quick to adapt", "found in every trade", "customs change from valley to valley",
        "stubborn about home ground", "many small kingdoms and quarrels", "marry young, work young",
    ),
    "elf": (
        "long-lived and slow to trust", "lean and light-footed", "keep long memories of old slights",
        "few children, born late in life", "keen-eyed at dusk", "speak an older tongue among themselves",
    ),
    "dwarf": (
        "stocky and hardy", "live in close-knit clans", "prize craft and kept oaths", "slow to forget a debt",
        "at home under stone", "beards and braids marked by clan",
    ),
    "orc": (
        "broad and strong", "blunt in speech", "standing won in open contests", "bands bound by kin",
        "often met with distrust", "heal hard wounds with scars worn proudly",
    ),
    "goblin": ("small and quick", "live in crowded warrens", "scavengers and tinkerers", "loud in numbers, wary alone"),
    "halfling": ("small and sure-footed", "love comfort and full larders", "close family ties", "hard to rattle"),
    "gnome": ("small and curious", "tinkerers and tale-keepers", "long-lived and talkative", "fond of riddles"),
    "giant": ("towering and slow to anger", "few in number", "live far from towns", "long memories of old borders"),
    "troll": ("huge and tough-hided", "slow to heal fire wounds", "keep to wild places", "feared by travellers"),
    "kobold": ("tiny and scaled", "live in tunnels", "skilled with traps", "loyal to their warren"),
    "beast": (
        "keen noses and sharp hearing", "fur, horns or scales by bloodline", "clan marks worn openly",
        "wary of crowded cities", "restless under a roof", "settle quarrels in the open",
    ),
    "spirit": (
        "a faint shimmer in bright light", "dream vividly and often", "uneasy around cold iron",
        "feel the dead nearby", "born rarely, to ordinary parents", "eyes that catch the light oddly",
    ),
    "sea": ("at home in cold water", "salt-cured skin", "keep the tides as a calendar", "distrust the deep inland"),
}
_RACE_TRAIT_WORDS = {
    "beast": ("beast", "cat", "wolf", "fox", "lizard", "serpent", "minotaur", "harpy"),
    "spirit": ("spirit", "fae", "fey", "ash", "touched", "blooded", "void"),
    "sea": ("mer", "tide", "seal", "sea", "river"),
}
_RACE_TRAITS_GENERAL = (
    "tight-knit families", "slow to trust outsiders", "keep old customs strictly", "tall and lean",
    "short and sturdy", "hardy in bad weather", "quick to laugh, quick to anger", "proud of their crafts",
    "live in scattered villages", "awake more by night than by day", "long memories for grudges",
    "few in number here", "travel in small bands", "settle disputes by elders' word",
)


def _trait_pool(race: str) -> list[str]:
    low = _norm(race)
    for word, traits in _RACE_TRAITS_BY_WORD.items():
        hints = _RACE_TRAIT_WORDS.get(word, (word,))
        if any(hint in low for hint in hints):
            return list(traits)
    return list(_RACE_TRAITS_GENERAL)


def roll_race_traits(race: str, rng: random.Random | None = None, n: int = 2, limit: int = 120) -> str:
    """Two or three short traits for one people, drawn by the engine."""
    rng = rng or random.Random()
    pool = _trait_pool(race)
    picked = rng.sample(pool, min(len(pool), max(1, n)))
    general = [trait for trait in _RACE_TRAITS_GENERAL if trait not in picked]
    if pool is not _RACE_TRAITS_GENERAL and general and rng.random() < 0.5:
        picked.append(rng.choice(general))
    text = ""
    for trait in picked:
        candidate = f"{text}, {trait}" if text else trait
        if len(candidate) > limit:
            break
        text = candidate
    return text


# Kinds of lore the post-start world-facts pass asks for. Each entry is
# "<fact kind>: <what to write>"; a few are drawn per call, so two worlds are
# not asked the same questions. These are asks, never sample answers.
_PHRASES["world_fact_ask"] = [
    *_plain((
        "faction: a group with a proper name, who leads it and what it wants",
        "faction: a rival of whoever rules here, named, and what it is after",
        "faction: a group people fear or whisper about, named, and what it does",
        "custom: a greeting, oath or courtesy people here use",
        "custom: how strangers are treated when they arrive",
        "custom: a festival or holy day and what is done on it",
        "custom: something taboo here and what happens to someone who breaks it",
        "custom: how the dead are buried or remembered",
        "custom: what ordinary people eat, drink or trade day to day",
        "custom: how people here prove their worth or honour",
        "history: an old war, fall or founding that people still talk about",
        "history: how the current rulers came to power",
        "history: a disaster within living memory and what it changed",
        "place_lore: a named place beyond the settlements and the story told about it",
        "place_lore: a road, river or ruin that travellers avoid, and why",
        "place_lore: where people gather to trade or settle disputes, and its name",
        "rule: a law about weapons, debts or trade, and who enforces it",
        "rule: who may own land or hold office, and who may not",
    )),
    *_plain((
        "magic: what using magic costs or risks here",
        "magic: how people without magic regard those who have it",
        "magic: who may teach magic, and what the law says about it",
    ), magic=SOME_MAGIC),
    *_plain((
        "place_lore: what sailors or fishers believe about the coast",
        "custom: what is owed to the sea or river before a voyage",
    ), water=True),
    *_plain(("history: what came before the current machines or industry",), era=NEW),
]

# ---------------------------------------------------------------------------
# Appearance: rolled values and pieces
# ---------------------------------------------------------------------------

_HAIR_COLOURS: list[Entry] = [
    *_plain((
        "black", "dark brown", "brown", "chestnut", "auburn", "copper", "red", "strawberry blonde",
        "sandy", "honey blonde", "ash blonde", "pale blonde", "mousy brown", "blue-black",
        "dark auburn", "light brown",
    )),
    *_plain(("grey", "salt-and-pepper", "white", "iron-grey"), age=("adult", "older")),
    *_plain(("dyed green", "dyed blue", "bleached", "dyed pink"), era=NEW),
    *_plain(("silver-blue", "violet-black", "frost-white"), magic=OPEN_MAGIC),
]
_HAIR_LENGTHS = ("cropped", "short", "chin-length", "shoulder-length", "long", "waist-length", "shaved close")
_HAIR_STYLES: list[Entry] = [
    *_plain((
        "worn loose", "tied back with a cord", "in a single braid", "in two braids", "curly", "wavy",
        "straight", "in a knot at the nape", "in twisted locks", "thick and unruly", "fine and flat",
        "in tight coils", "swept back", "parted in the middle", "falling over one eye",
        "in a crown of braids", "cut ragged", "half tied up", "pinned under a scarf",
    )),
    *_plain(("in cornrows", "in an undercut", "slicked with oil"), era=("industrial",) + NEW),
    *_plain(("in a topknot",), era=PRE),
]
_EYE_COLOURS: list[Entry] = [
    *_plain((
        "brown", "dark brown", "hazel", "green", "grey", "blue", "blue-grey", "black", "amber",
        "green-brown", "pale blue", "grey-green", "light brown", "deep blue",
    )),
    *_plain(("gold-flecked", "faintly glowing violet", "silver"), magic=OPEN_MAGIC),
    *_plain(("one natural, one cybernetic",), era=FUT),
]
_FACE_MARKS: list[Entry] = [
    *_plain((
        "a thin scar through one eyebrow", "a chipped front tooth", "a nose broken once and set crooked",
        "freckles across the nose", "a mole above the lip", "pockmarks on the cheeks", "a notched ear",
        "deep laugh lines", "a birthmark along the jaw", "a split lip, long healed",
        "a burn mark on one temple", "a cleft chin", "heavy brows that nearly meet",
        "a small scar on the chin", "a gap between the front teeth", "sun-creased skin",
    )),
    *_plain(("a faded ink mark under one eye", "a pierced eyebrow"), era=("industrial",) + NEW),
    *_plain(("a ritual dot painted on the brow",), era=PRE),
]
# One pick per feature, so a face never gets "a soft jaw, a square jaw".
_FACE_OTHER: dict[str, tuple[str, ...]] = {
    "jaw": ("a soft jaw", "a square jaw", "a sharp chin", "a narrow jaw", "a heavy jaw"),
    "nose": ("a narrow nose", "a broad nose", "a hooked nose", "a snub nose", "a long straight nose"),
    "face": ("a round face", "a long face", "high cheekbones", "full cheeks", "hollow cheeks", "a heart-shaped face"),
    "mouth": ("thin lips", "a wide mouth", "a quick smile", "a downturned mouth", "full lips"),
    "brows": ("straight brows", "arched brows", "thick brows", "sparse brows"),
    "look": ("deep-set eyes", "heavy-lidded eyes", "a weathered look", "a guarded stare", "a steady gaze", "dimples"),
}
_CLOTHES_COLOURS: list[Entry] = [
    *_plain((
        "undyed", "brown", "grey", "dark green", "faded blue", "rust red", "ochre", "black", "cream",
        "slate", "moss green", "deep red", "charcoal", "tan", "dun",
    )),
    *_plain(("navy", "olive", "khaki", "white"), era=("industrial",) + NEW),
    *_plain(("high-vis orange", "matte black", "reflective grey"), era=NEW),
]
_CLOTHES_WEAR = ("worn but clean", "patched", "nearly new", "travel-stained", "mended many times", "well kept", "frayed at the edges")

_CLOTHES: dict[str, list[Entry]] = {
    "torso": [
        *_plain(("linen shirt", "wool tunic", "laced bodice", "leather jerkin", "smock", "kirtle", "doublet", "quilted vest", "wrap shirt"), era=PRE),
        *_plain(("collared shirt", "waistcoat over shirt", "high-necked blouse", "work shirt", "apron dress"), era=IND),
        *_plain(("t-shirt", "hoodie", "button-down shirt", "sweater", "tank top", "polo shirt", "blouse", "flannel shirt"), era=MOD),
        *_plain(("thermal undersuit", "compression shirt", "padded work top", "mesh-weave shirt", "utility tunic"), era=FUT),
    ],
    "outer": [
        *_plain(("hooded cloak", "wool mantle", "oilcloth cape", "sheepskin coat", "short cape"), era=PRE),
        _e("fur-lined cloak", era=PRE, climate=("cold",)),
        _e("light hooded robe", era=PRE, climate=("hot",)),
        *_plain(("frock coat", "long duster", "pea coat", "knitted shawl", "overcoat"), era=IND),
        *_plain(("denim jacket", "rain jacket", "puffer jacket", "blazer", "leather jacket", "parka"), era=MOD),
        *_plain(("pressure-rated coverall", "insulated parka", "utility vest", "rain poncho with light strips"), era=FUT),
    ],
    "legs": [
        *_plain(("wool hose", "breeches", "linen trousers", "long skirt", "wrap skirt", "leggings"), era=PRE),
        *_plain(("wool trousers", "canvas trousers", "long skirt", "trousers with braces"), era=IND),
        *_plain(("jeans", "cargo pants", "chinos", "leggings", "skirt", "work trousers"), era=MOD),
        *_plain(("cargo leggings", "synth-weave trousers", "padded work trousers"), era=FUT),
    ],
    "feet": [
        *_plain(("turnshoes", "ankle boots", "wooden clogs", "foot wraps", "soft leather shoes", "riding boots"), era=PRE),
        _e("sandals", era=PRE, climate=("hot", "temperate")),
        _e("fur-lined boots", era=PRE, climate=("cold",)),
        *_plain(("hobnailed boots", "lace-up boots", "button boots", "work boots"), era=IND),
        *_plain(("sneakers", "work boots", "loafers", "running shoes", "ankle boots"), era=MOD),
        _e("sandals", era=MOD, climate=("hot", "temperate")),
        *_plain(("mag-soled boots", "grip-sole shoes", "sealed boots"), era=FUT),
    ],
    "head": [
        *_plain(("linen coif", "felt hat", "straw hat", "headscarf", "wool hood"), era=PRE),
        *_plain(("bowler hat", "flat cap", "bonnet", "slouch hat"), era=IND),
        *_plain(("baseball cap", "beanie", "bandana"), era=MOD),
        *_plain(("visor", "hood with a filter mask"), era=FUT),
    ],
    "hands": [
        *_plain(("leather gloves", "fingerless mitts"), era=OLD),
        *_plain(("bike gloves", "work gloves"), era=MOD),
        *_plain(("tactile gloves", "insulated gloves"), era=FUT),
    ],
    "waist": [
        *_plain(("rope belt", "leather belt with a pouch", "cloth sash"), era=PRE),
        *_plain(("belt with a watch chain", "braces"), era=IND),
        *_plain(("canvas belt", "belt bag"), era=MOD),
        *_plain(("tool belt", "cable harness"), era=FUT),
    ],
    "bag": [
        *_plain(("shoulder satchel", "belt pouch", "knapsack", "wicker basket"), era=PRE),
        *_plain(("carpet bag", "leather satchel", "doctor's bag"), era=IND),
        *_plain(("backpack", "tote bag", "messenger bag"), era=MOD),
        *_plain(("sling pack", "sealed case"), era=FUT),
    ],
}
_CARRIED: list[Entry] = [
    *_plain(("tinderbox", "whetstone", "waterskin", "heel of bread", "small knife", "copper coins", "wooden spoon", "needle and thread", "prayer beads", "sling"), era=PRE),
    *_plain(("pocket watch", "matches", "tin cup", "folding knife", "a few coins", "pencil stub", "train ticket", "tobacco tin"), era=IND),
    *_plain(("phone with a cracked screen", "house keys", "wallet", "water bottle", "lighter", "earbuds", "transit card", "granola bar"), era=MOD),
    *_plain(("ration bar", "ID chip", "multitool", "water flask", "credit stick", "work tablet", "filter mask"), era=FUT),
]


# ---------------------------------------------------------------------------
# Proficiency names (playtest #22)
# ---------------------------------------------------------------------------
# The shape of a proficiency name: a noun naming a craft, a body of lore, a
# field skill, a way with people or a magical practice. custom_skills asks
# with no samples came back as verb slogans ("master the dance of shadows,
# learn from the ancients, forge unbreakable bonds"). Each roll now shows a
# few of these, drawn per call, one per category, filtered by the world.

_PROFICIENCY_NAMES: list[Entry] = [
    # craft and trade
    *_plain((
        "Carpentry", "Rope Splicing", "Leatherworking", "Basket Weaving", "Tailoring", "Cooking",
        "Bookkeeping", "Trap Making", "Knot Tying", "Sewing", "Woodcarving", "Butchery",
    ), cat="craft"),
    *_plain((
        "Joinery", "Cooperage", "Candle Making", "Tanning", "Smithing", "Fletching", "Pottery",
        "Glassblowing", "Dyeing", "Brewing", "Masonry", "Thatching", "Wheelwrighting", "Bookbinding",
        "Cobbling", "Charcoal Burning", "Bonesetting", "Cheesemaking", "Ink Making", "Mapmaking",
    ), cat="craft", era=OLD),
    *_plain(("Bowyery", "Calligraphy", "Embroidery", "Herbalism"), cat="craft", era=PRE),
    *_plain(("Clock Repair", "Typesetting", "Telegraphy", "Gunsmithing", "Machining", "Boiler Tending", "Photography"),
            cat="craft", era=IND),
    *_plain(("Electrical Repair", "Auto Mechanics", "Welding", "Plumbing", "Programming", "First Aid", "Sound Engineering"),
            cat="craft", era=MOD),
    *_plain(("Drone Repair", "Hull Patching", "Circuit Salvage", "Fabricator Tuning", "Hydroponics", "Reactor Tending",
             "Suit Maintenance"), cat="craft", era=FUT),
    *_plain(("Net Mending", "Sail Mending", "Boatbuilding", "Rigging"), cat="craft", water=True, era=OLD),
    _e("Rigging", cat="craft", era=NEW),
    # lore and learning
    *_plain(("Local History", "Weather Lore", "Beast Lore", "Mineral Lore", "Genealogy", "Arithmetic", "Cartography",
             "Folk Remedies"), cat="lore"),
    *_plain(("Herb Lore", "Heraldry", "Old Scripts", "Guild Law", "Temple Rites", "Star Reading", "Alchemy"),
            cat="lore", era=OLD),
    *_plain(("Forensics", "Chemistry", "Urban Geography", "Criminal Law"), cat="lore", era=MOD),
    *_plain(("Xenobiology", "Station Protocols", "Astrogation", "Data Forensics"), cat="lore", era=FUT),
    *_plain(("Tide Lore", "Ship Signals"), cat="lore", water=True),
    # field and body
    *_plain(("Tracking", "Foraging", "Climbing", "Stealth", "Knife Fighting", "Wrestling", "Animal Handling",
             "Lockpicking", "Mountaineering"), cat="field"),
    *_plain(("Snaring", "Archery", "Swordplay", "Horsemanship", "Spear Fighting"), cat="field", era=OLD),
    *_plain(("Quarterstaff", "Falconry"), cat="field", era=PRE),
    *_plain(("Marksmanship",), cat="field", era=("industrial", "modern", "future")),
    *_plain(("Driving", "Free Running"), cat="field", era=MOD),
    *_plain(("Zero-G Movement", "Piloting", "Vacuum Survival"), cat="field", era=FUT),
    *_plain(("Swimming", "Sailing", "Rowing", "Fishing"), cat="field", water=True),
    _e("Cold Survival", cat="field", climate="cold"),
    _e("Desert Survival", cat="field", climate="hot"),
    # people
    *_plain(("Haggling", "Storytelling", "Etiquette", "Interrogation", "Disguise", "Forgery", "Gambling", "Oratory",
             "Street Cant", "Bargaining"), cat="people"),
    *_plain(("Balladry", "Fortune Telling"), cat="people", era=OLD),
    # magic: only where the world has it
    *_plain(("Ward Drawing", "Rune Carving", "Hedge Magic", "Potion Brewing", "Scrying", "Glyph Reading"),
            cat="magic", magic=SOME_MAGIC),
    *_plain(("Enchanting", "Charm Weaving", "Ley Sensing"), cat="magic", magic=("common utility",)),
    *_plain(("Qi Circulation", "Pill Refining", "Talisman Drawing", "Formation Arrays", "Sword Intent"),
            cat="magic", magic=("cultivation",)),
]
_PROFICIENCY_CATEGORIES = ("craft", "lore", "field", "people", "magic")


def _stems(text: str) -> set[str]:
    return {word[:5] for word in re.findall(r"[a-z]{4,}", _norm(text))}


def draw_proficiency_names(
    context: dict[str, Any] | None = None,
    n: int = 4,
    rng: random.Random | None = None,
    exclude: Iterable[Any] = (),
) -> list[str]:
    """Proficiency name shapes for one call: one per category, fitting the world.

    When ``context["backstory"]`` names a trade (a carpenter, a sailor), one
    draw is taken from the names that share a word with it, so the shapes
    fit the character as well as the world.
    """
    rng = rng or random.Random()
    ctx = dict(context or {})
    full, _tokens = _excluded(exclude)
    if not _norm(ctx.get("magic")):
        # Unknown magic draws no magical practice: magic only where the world has it.
        ctx["magic"] = "none"
    pool = [
        (text, tags) for text, tags in _PROFICIENCY_NAMES
        if _fits({k: v for k, v in tags.items() if k != "cat"}, ctx) and _norm(text) not in full
    ]
    out: list[str] = []
    backstory = _stems(ctx.get("backstory") or "")
    if backstory:
        near = [text for text, _tags in pool if _stems(text) & backstory]
        if near:
            out.append(rng.choice(near))
    categories = list(_PROFICIENCY_CATEGORIES)
    rng.shuffle(categories)
    for category in categories:
        if len(out) >= n:
            break
        choices = [text for text, tags in pool if tags.get("cat") == category and text not in out]
        if choices:
            out.append(rng.choice(choices))
    rest = [text for text, _tags in pool if text not in out]
    out += _sample(rng, rest, n - len(out))
    return out[:n]


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

_COLD_WORDS = ("arctic", "frozen", "snow", "tundra", "glacier", "winter", "icy", "frost", "boreal")
_HOT_WORDS = ("desert", "tropical", "jungle", "sun-scorched", "arid", "dune", "savanna", "scorching", "oasis")
_WATER_WORDS = (
    "harbor", "harbour", "dock", "wharf", "quay", "port", "coast", "shore", "beach", "fishing",
    "river", "lake", "ferry", "pier", "fjord", "island", "seaside", "sea ", "marsh", "canal",
)


def age_band(age: Any) -> str:
    text = _norm(age)
    if not text:
        return ""
    match = re.search(r"\d+", text)
    if match:
        years = int(match.group(0))
        return "young" if years < 30 else ("adult" if years < 50 else "older")
    if any(word in text for word in ("old", "elder", "aged", "grey", "senior")):
        return "older"
    if any(word in text for word in ("middle",)):
        return "adult"
    if any(word in text for word in ("young", "teen", "youth")):
        return "young"
    return ""


def _climate(text: str) -> str:
    blob = _norm(text)
    if any(word in blob for word in _COLD_WORDS):
        return "cold"
    if any(word in blob for word in _HOT_WORDS):
        return "hot"
    return "temperate" if blob else ""


def _has_water(text: str) -> bool:
    blob = f" {_norm(text)} "
    return any(re.search(rf"\b{re.escape(word.strip())}", blob) for word in _WATER_WORDS)


def _place_kind(text: str) -> str:
    try:
        from app.world import _SEED_POOL_HINTS

        low = _norm(text)
        scores = {pool: sum(1 for word in words if word in low) for pool, words in _SEED_POOL_HINTS}
        best = max(scores, key=lambda pool: (scores[pool], pool == "settlement"))
        return best if scores[best] else "settlement"
    except Exception:
        return "settlement"


def world_context(
    options: dict[str, Any] | None = None,
    *,
    location: dict[str, Any] | None = None,
    sex: str = "",
    age: Any = "",
) -> dict[str, Any]:
    """What the pools need to know about a world, a place and a person.

    ``options`` is a setup form or ``playthrough_options``; ``location`` a
    current_location dict (name, summary, settlement_size).
    """
    opts = options if isinstance(options, dict) else {}
    style_text = " ".join(
        str(opts.get(key) or "")
        for key in ("world_style", "custom_style", "start_location", "_randomize_idea", "world_races")
    )
    try:
        from app.world import resolve_world_era, resolve_world_magic

        era = resolve_world_era(str(opts.get("tech_level") or ""), str(opts.get("world_style") or ""), str(opts.get("custom_style") or ""))
        magic = resolve_world_magic(str(opts.get("magic_level") or ""), str(opts.get("world_style") or ""), str(opts.get("custom_style") or ""))
    except Exception:
        era, magic = "preindustrial", str(opts.get("magic_level") or "")
    ctx: dict[str, Any] = {
        "era": era if era in ERAS else "preindustrial",
        "magic": _norm(magic),
        "culture": detect_culture(style_text, era),
        "climate": _climate(style_text),
        "world_water": _has_water(style_text),
        "sex": _norm(sex) if _norm(sex) in ("female", "male") else "",
        "age": age_band(age),
    }
    if isinstance(location, dict) and (location.get("name") or location.get("summary")):
        place_text = f"{location.get('name') or ''} {location.get('summary') or ''}"
        ctx["place"] = _place_kind(place_text)
        ctx["water"] = ctx["place"] == "water" or _has_water(place_text)
        size = str(location.get("settlement_size") or "")
        try:
            from app.venues import normalize_settlement_size

            size = normalize_settlement_size(size)
        except Exception:
            pass
        ctx["size"] = size
        ctx["place_name"] = str(location.get("name") or "")
    else:
        # A setup roll has no current place: water is the world's.
        ctx["water"] = ctx["world_water"]
    return ctx


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _pool(kind: str, ctx: dict[str, Any]) -> list[str]:
    if kind == "npc_role":
        era = ctx.get("era") or "preindustrial"
        place = ctx.get("place") or "settlement"
        # A harbour town is still a town: its bakers stand beside its boatmen.
        places = [place, "settlement"] if place == "water" and ctx.get("size") else [place]
        entries: list[Entry] = []
        for one in places:
            entries += _base_roles(era, one) + [
                entry for entry in _ROLE_EXTRAS if one in (entry[1].get("place") or (one,))
            ]
        match_ctx = {**ctx, "place": place}
        out: list[str] = []
        for text, tags in entries:
            # A role tagged only by magic fits any era unless the role says otherwise.
            tags = {key: value for key, value in tags.items() if key != "place"}
            if _fits(tags, match_ctx) and text not in out:
                out.append(text)
        return out
    if kind in _PHRASES:
        return [text for text, tags in _PHRASES[kind] if _fits(tags, ctx)]
    raise KeyError(kind)


def _sample(rng: random.Random, items: list[str], n: int) -> list[str]:
    if n <= 0 or not items:
        return []
    return rng.sample(items, min(n, len(items)))


def _excluded(exclude: Iterable[Any]) -> tuple[set[str], set[str]]:
    full = {_norm(item) for item in exclude or () if _norm(item)}
    tokens: set[str] = set()
    for item in full:
        tokens |= _name_tokens(item)
    return full, tokens


def draw_names(
    context: dict[str, Any] | None = None,
    n: int = 4,
    rng: random.Random | None = None,
    exclude: Iterable[Any] = (),
    *,
    sex: str = "",
    family: bool = True,
) -> list[str]:
    """Fresh personal names. No part of an excluded name is drawn again."""
    rng = rng or random.Random()
    ctx = dict(context or {})
    culture = str(ctx.get("culture") or "common")
    full, tokens = _excluded(exclude)
    sexes: list[str]
    want = _norm(sex or ctx.get("sex"))
    if want in ("female", "male"):
        sexes = [want] * n
    else:
        # The first sex is rolled: alternating from "female" made every
        # single draw (n=1, the engine's own NPCs) a woman's name.
        first = rng.randrange(2)
        sexes = [("female", "male")[(i + first) % 2] for i in range(n)]
        rng.shuffle(sexes)
    out: list[str] = []
    used_given: set[str] = set()
    used_family: set[str] = set()
    for one_sex in sexes:
        givens = [g for g in _given_names(culture, one_sex) if _norm(g) not in tokens and _norm(g) not in used_given]
        if not givens:
            break
        given = rng.choice(givens)
        used_given.add(_norm(given))
        surname = ""
        if family:
            families = [
                f for f in _family_names(culture, one_sex)
                if not (_name_tokens(f) & tokens) and _norm(f) not in used_family
            ]
            if families:
                surname = rng.choice(families)
                used_family.add(_norm(surname))
        name = _render_name(culture, given, surname)
        if _norm(name) not in full:
            out.append(name)
    return out


# Words that cannot stand for a place in "{place}": a venue name never ends on one.
_VENUE_CLOSED_WORDS = frozenset({
    "the", "a", "an", "of", "at", "in", "on", "to", "by", "and", "or", "for", "from", "with", "near",
    "over", "under", "upon", "into", "this", "that", "its", "his", "her", "their", "our", "my", "your",
})


def _venue_place_word(place_name: str) -> str:
    """The place's own proper word for "{place}", or "".

    Live gate N1: the first word was taken, so "The Refugees' Trail" gave
    "The Kettle at The"; the draft used it as the town's name, MOVE and
    LOC_NEW stored it and a shopkeeper was named "Mira Kettle" after it.
    """
    out = []
    for raw in str(place_name or "").split():
        word = raw.strip(",.;:!?\"()[]")
        for suffix in ("'s", "\u2019s"):
            if word.endswith(suffix):
                word = word[: -len(suffix)]
        word = word.strip("'\u2019")
        if word and word.lower() not in _VENUE_CLOSED_WORDS and word[:1].isupper():
            out.append(word)
    return out[0] if out else ""


def venue_trade_words(kind: str, era: str) -> list[str]:
    """A venue kind's own trade words for a sign, title-cased, only those the era has."""
    try:
        from app.venues import _KIND_WORDS
    except Exception:
        return []
    era = str(era or "").strip().lower()
    out: list[str] = []
    for word in _KIND_WORDS.get(str(kind or ""), ()):
        eras = _TRADE_WORD_ERAS.get(word)
        if era and eras and era not in eras:
            continue
        out.append(" ".join(part[:1].upper() + part[1:] for part in word.split()))
    return out


def _render_venue(form: str, ctx: dict[str, Any], rng: random.Random, exclude_tokens: set[str]) -> str:
    era = ctx.get("era") or "preindustrial"
    group = "new" if era in NEW else "old"
    nouns = list(_VENUE_NOUN[group])
    noun = rng.choice(nouns)
    noun2 = rng.choice([x for x in nouns if x != noun])
    family_pool = _family_names(str(ctx.get("culture") or "common"), "male")
    if exclude_tokens:
        family_pool = [f for f in family_pool if _norm(f) not in exclude_tokens]
    place = _venue_place_word(str(ctx.get("place_name") or "")) or rng.choice(nouns)
    kind = str(ctx.get("venue_kind") or "")
    trades = venue_trade_words(kind, str(era)) if kind else []
    return form.format(
        adj=rng.choice(_VENUE_ADJ[group]),
        noun=noun,
        noun2=noun2,
        trade=rng.choice(trades) if trades else rng.choice(_VENUE_TRADE.get(era) or _VENUE_TRADE["preindustrial"]),
        family=rng.choice(family_pool) if family_pool else rng.choice(nouns),
        place=place,
        street=str(ctx.get("street_name") or ""),
    )


def _venue_forms(ctx: dict[str, Any]) -> list[str]:
    """The venue forms this context may draw.

    Without ``venue_kind`` and ``street_name`` this is exactly the list the
    draft's cast_options always drew from, so its seeded draws do not move.
    """
    kind = str(ctx.get("venue_kind") or "")
    has_street = bool(str(ctx.get("street_name") or "").strip())
    # True: only "{street}" forms; False: none of them; absent: either.
    street_form = ctx.get("street_form")
    forms: list[str] = []
    for text, tags in _VENUE_FORMS:
        if not _fits(tags, ctx):
            continue
        if "{street}" in text and not has_street:
            continue
        if street_form is True and "{street}" not in text:
            continue
        if street_form is False and "{street}" in text:
            continue
        if kind and "{trade}" not in text and kind not in SIGN_FORM_KINDS:
            continue
        forms.append(text)
    return forms


def _venue_name_fits(text: str, form: str, kind: str) -> bool:
    """A drawn plot name must read as its own kind, or be a sign on an inn, tavern or bar."""
    try:
        from app.venues import venue_kind_from_name
    except Exception:
        return True
    found = venue_kind_from_name(text)
    if found == kind:
        return True
    return "{trade}" not in form and kind in SIGN_FORM_KINDS and found == ""


def _render_street(form: str, ctx: dict[str, Any], rng: random.Random) -> str:
    era = ctx.get("era") or "preindustrial"
    group = "new" if era in NEW else "old"
    nouns = list(_VENUE_NOUN[group])
    family_pool = _family_names(str(ctx.get("culture") or "common"), "male")
    return form.format(
        noun=rng.choice(nouns),
        adj=rng.choice(_VENUE_ADJ[group]),
        family=rng.choice(family_pool) if family_pool else rng.choice(nouns),
        tail=rng.choice(_STREET_TAIL[group]),
    )


_IRREGULAR_PLURALS = {"elf": "elves", "dwarf": "dwarves", "half-elf": "half-elves", "wood elf": "wood elves", "hill dwarf": "hill dwarves"}


def _plural(race: str) -> str:
    low = race.strip()
    if low.lower() in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[low.lower()]
    if re.search(r"(s|folk|kin|born|blooded|fae|people)$", low, re.I):
        return low
    return f"{low}s"


def _render_race_rules(kind: str, ctx: dict[str, Any], rng: random.Random, n: int) -> list[str]:
    races = [r.strip() for r in str(ctx.get("races") or "").split(",") if r.strip()]
    if not races:
        races = ["humans"]
    phrases = list(_RACE_MAGIC_RULES if kind == "race_magic_rules" else _RACE_ABILITY_RULES)
    if ctx.get("magic") == "none" and kind == "race_magic_rules":
        phrases = [p for p in phrases if "no magic" in p or "cannot cast" in p or "barred" in p]
    out: list[str] = []
    for _ in range(n):
        picked = rng.sample(phrases, min(len(phrases), min(3, len(races))))
        parts = []
        for race, phrase in zip(races[:3], picked):
            parts.append(phrase.format(race=_plural(race).capitalize()))
        out.append("; ".join(parts) + ".")
    return out


def _render_clothes(ctx: dict[str, Any], rng: random.Random, rolled: dict[str, Any] | None = None) -> str:
    slots = ["torso", "legs", "feet"] + rng.sample(["outer", "head", "hands", "waist", "bag"], 2)
    parts = []
    colour = (rolled or {}).get("main_colour")
    for i, slot in enumerate(slots):
        items = [text for text, tags in _CLOTHES[slot] if _fits(tags, ctx)]
        if not items:
            continue
        item = rng.choice(items)
        if i == 0 and colour:
            item = f"{colour} {item}"
        parts.append(f"{slot}: {item}")
    return "; ".join(parts)


def _render_kit(ctx: dict[str, Any], rng: random.Random) -> str:
    worn = []
    for slot in ("torso", "feet"):
        items = [text for text, tags in _CLOTHES[slot] if _fits(tags, ctx)]
        if items:
            worn.append(rng.choice(items))
    carried = [text for text, tags in _CARRIED if _fits(tags, ctx)]
    return ", ".join(worn + _sample(rng, carried, 2 + rng.randint(0, 2)))


def _render_hair(ctx: dict[str, Any], rng: random.Random, rolled: dict[str, Any] | None) -> str:
    rolled = rolled or {}
    colour = rolled.get("hair_colour") or rng.choice([t for t, g in _HAIR_COLOURS if _fits(g, ctx)])
    length = rolled.get("hair_length") or rng.choice(_HAIR_LENGTHS)
    style = rng.choice([t for t, g in _HAIR_STYLES if _fits(g, ctx)])
    if length == "shaved close":
        return f"{colour} hair shaved close"
    return f"{length} {colour} hair, {style}"


def _render_face(ctx: dict[str, Any], rng: random.Random, rolled: dict[str, Any] | None) -> str:
    rolled = rolled or {}
    eyes = rolled.get("eye_colour") or rng.choice([t for t, g in _EYE_COLOURS if _fits(g, ctx)])
    features = rng.sample(list(_FACE_OTHER), 2)
    bits = [f"{eyes} eyes", *(rng.choice(_FACE_OTHER[feature]) for feature in features)]
    mark = rolled.get("notable_mark")
    if mark and mark != "none":
        bits.append(mark)
    return ", ".join(bits)


RENDERED_KINDS = ("person_name", "venue_name", "street_name", "hair", "facial_features", "appearance", "starter_equipment", "race_magic_rules", "race_ability_rules", "proficiency_name")
DRAWN_KINDS = ("npc_role", *sorted(_PHRASES))
KINDS = (*DRAWN_KINDS, *RENDERED_KINDS)


def draw(
    kind: str,
    context: dict[str, Any] | None = None,
    n: int = 4,
    rng: random.Random | None = None,
    exclude: Iterable[Any] = (),
    *,
    accept: Callable[[str], bool] | None = None,
    max_attempts: int | None = None,
) -> list[str]:
    """``n`` fresh entries of ``kind`` that fit ``context`` and are not in ``exclude``.

    Deterministic for a seeded ``rng``. Pool order is fixed (lists, not sets),
    so the same seed and context always give the same draw.

    For rendered kinds, ``accept`` may veto a rendered entry before the fit
    checks run (the town grid uses it to keep a name inside the one city cell
    that owns it), and ``max_attempts`` replaces the default ``n * 8`` renders.
    """
    rng = rng or random.Random()
    ctx = dict(context or {})
    n = max(0, int(n))
    if kind == "person_name":
        return draw_names(ctx, n, rng, exclude)
    if kind == "proficiency_name":
        return draw_proficiency_names(ctx, n, rng, exclude)
    full, tokens = _excluded(exclude)
    if kind in DRAWN_KINDS:
        pool = [item for item in _pool(kind, ctx) if _norm(item) not in full]
        return _sample(rng, pool, n)
    rolled = ctx.get("rolled") if isinstance(ctx.get("rolled"), dict) else None
    out: list[str] = []
    attempts = 0
    limit = int(max_attempts) if max_attempts else n * 8
    venue_forms = _venue_forms(ctx) if kind == "venue_name" else []
    street_forms = [text for text, tags in _STREET_FORMS if _fits(tags, ctx)] if kind == "street_name" else []
    if (kind == "venue_name" and not venue_forms) or (kind == "street_name" and not street_forms):
        return []
    while len(out) < n and attempts < limit:
        attempts += 1
        if kind == "venue_name":
            form = rng.choice(venue_forms)
            text = _render_venue(form, ctx, rng, tokens)
            if accept is not None and not accept(text):
                continue
            if text.split()[-1].lower() in _VENUE_CLOSED_WORDS:
                continue  # a name cut mid-phrase is no name
            venue_kind = str(ctx.get("venue_kind") or "")
            if venue_kind and not _venue_name_fits(text, form, venue_kind):
                continue  # a bakery is never "Blind Owl Smithy"
        elif kind == "street_name":
            text = _render_street(rng.choice(street_forms), ctx, rng)
            if accept is not None and not accept(text):
                continue
        elif kind == "hair":
            text = _render_hair(ctx, rng, rolled)
        elif kind == "facial_features":
            text = _render_face(ctx, rng, rolled)
        elif kind == "appearance":
            text = _render_clothes(ctx, rng, rolled)
        elif kind == "starter_equipment":
            text = _render_kit(ctx, rng)
        elif kind in ("race_magic_rules", "race_ability_rules"):
            text = _render_race_rules(kind, ctx, rng, 1)[0]
        else:
            raise KeyError(kind)
        if _norm(text) in full or text in out:
            continue
        out.append(text)
    return out


# ---------------------------------------------------------------------------
# Engine-rolled hard values
# ---------------------------------------------------------------------------

ROLLED_FIELDS = ("hair", "facial_features", "appearance")


def roll_values(field: str, context: dict[str, Any] | None = None, rng: random.Random | None = None) -> dict[str, str]:
    """The hard facts of an appearance field, decided by the engine."""
    rng = rng or random.Random()
    ctx = dict(context or {})
    if field == "hair":
        return {
            "hair_colour": rng.choice([t for t, g in _HAIR_COLOURS if _fits(g, ctx)]),
            "hair_length": rng.choice(_HAIR_LENGTHS),
        }
    if field == "facial_features":
        marks = [t for t, g in _FACE_MARKS if _fits(g, ctx)]
        # About a third of faces have nothing worth noting.
        mark = "none" if rng.random() < 0.35 else rng.choice(marks)
        return {
            "eye_colour": rng.choice([t for t, g in _EYE_COLOURS if _fits(g, ctx)]),
            "notable_mark": mark,
        }
    if field == "appearance":
        return {
            "main_colour": rng.choice([t for t, g in _CLOTHES_COLOURS if _fits(g, ctx)]),
            "condition": rng.choice(_CLOTHES_WEAR),
        }
    return {}


ROLLED_RULE = (
    "engine_rolled holds facts the engine already decided for this field. Write the field's text around "
    "them: use every one as given, change none, and add the rest yourself."
)


def _key_word(value: str) -> str:
    words = [w for w in re.findall(r"[a-z]+", _norm(value)) if w not in {"a", "an", "the", "one", "on", "of", "and", "set", "once", "between", "along", "across", "through", "above", "under", "long"}]
    return max(words, key=len) if words else ""


def _has_term(text: str, term: str, after: str = "") -> bool:
    return re.search(rf"(?<![\w-]){re.escape(_norm(term))}(?![\w-]){after}", _norm(text)) is not None


def _swap_term(text: str, rolled: str, known: Iterable[str], after: str = "") -> str:
    """``text`` with the first other known value replaced by ``rolled``; '' when none is there.

    The model kept its own value and the rolled one was put beside it:
    "auburn hair, long black curls", "waist-length shoulder-length".
    """
    for other in sorted({str(k) for k in known}, key=len, reverse=True):
        if _norm(other) == _norm(rolled):
            continue
        found = re.search(rf"(?<![\w-]){re.escape(other)}(?![\w-]){after}", text, flags=re.I)
        if found:
            return text[: found.start()] + rolled + text[found.start() + len(other):]
    return ""


def apply_rolled_values(field: str, value: Any, rolled: dict[str, Any] | None) -> Any:
    """Make the text carry the rolled values: a different value of the same kind is
    swapped for the rolled one, a missing one is added. Nothing else is removed."""
    if not rolled or not isinstance(value, str):
        return value
    text = value.strip()
    if field == "hair":
        colour = str(rolled.get("hair_colour") or "")
        length = str(rolled.get("hair_length") or "")
        if colour and not _has_term(text, colour):
            swapped = _swap_term(text, colour, (t for t, _ in _HAIR_COLOURS))
            text = swapped or (f"{colour} hair, {text}" if text else f"{length} {colour} hair".strip())
        if length and not _has_term(text, length):
            swapped = _swap_term(text, length, _HAIR_LENGTHS)
            text = swapped or f"{length} {text}"
        return text
    if field == "facial_features":
        eyes = str(rolled.get("eye_colour") or "")
        mark = str(rolled.get("notable_mark") or "")
        low = _norm(text)
        if eyes and not _has_term(text, eyes):
            swapped = _swap_term(text, eyes, (t for t, _ in _EYE_COLOURS), after=r"(?=\s+eyes?\b)")
            text = swapped or (f"{eyes} eyes, {text}" if text else f"{eyes} eyes")
        if mark and mark != "none" and _key_word(mark) not in low:
            text = f"{text}, {mark}" if text else mark
        return text
    if field == "appearance":
        colour = str(rolled.get("main_colour") or "")
        low = _norm(text)
        if colour and _key_word(colour) not in low:
            text = f"{text}; colour: {colour}" if text else f"colour: {colour}"
        return text
    return value


def roll_setup_values(
    return_fields: Iterable[str],
    setup: dict[str, Any] | None,
    locked_fields: Iterable[str] = (),
    rng: random.Random | None = None,
) -> dict[str, dict[str, str]]:
    """Rolls for the appearance fields this request will write (never a locked one)."""
    rng = rng or random.Random()
    locked = set(locked_fields or ())
    setup = setup if isinstance(setup, dict) else {}
    ctx = setup_context(setup)
    return {
        field: roll_values(field, ctx, rng)
        for field in return_fields
        if field in ROLLED_FIELDS and field not in locked
    }


# ---------------------------------------------------------------------------
# Setup examples (playtest #26)
# ---------------------------------------------------------------------------

# FIELD_CONTRACTS[field]["example_pool"] names the kind; this maps the rest.
SETUP_FIELD_KINDS = {
    "economy": "economy",
    "world_races": "world_races",
    "race_magic_rules": "race_magic_rules",
    "race_ability_rules": "race_ability_rules",
    "skill_style": "skill_style",
    "npc_density": "npc_density",
    "quest_style": "quest_style",
    "faction_pressure": "faction_pressure",
    "npc_stat_scaling": "npc_stat_scaling",
    "npc_skill_frequency": "npc_skill_frequency",
    "rank_scale": "rank_scale",
    "hair": "hair",
    "facial_features": "facial_features",
    "appearance": "appearance",
    "starter_equipment": "starter_equipment",
    "player_sex": "player_sex",
    "previous_life_sex": "previous_life_sex",
    "player_name": "person_name",
    "custom_skills": "proficiency_name",
}

EXAMPLES_RULE = (
    "Examples drawn fresh for this roll from a large pool (a few of many, different every time). "
    "Use one if it fits this world, adapt it, or write your own."
)

# Per-field wording where "use one" would be wrong (playtest #22): the drawn
# proficiency names show the form a name takes, not this character's skills.
FIELD_EXAMPLES_RULES = {
    "custom_skills": (
        "Proficiency names drawn fresh for this roll from a large pool, to show the form a name takes: a noun "
        "naming a craft, a lore, a field skill, a way with people or a practice, never a verb phrase. Name this "
        "character's own proficiencies in that form; take one only if it fits the backstory."
    ),
}


def examples_rule(field: str) -> str:
    return FIELD_EXAMPLES_RULES.get(field, EXAMPLES_RULE)


def setup_context(setup: dict[str, Any] | None) -> dict[str, Any]:
    setup = setup if isinstance(setup, dict) else {}
    ctx = world_context(setup, sex=str(setup.get("player_sex") or ""), age=setup.get("player_age"))
    ctx["races"] = str(setup.get("world_races") or "")
    ctx["backstory"] = str(setup.get("character_backstory") or "")[:1200]
    return ctx


def setup_examples(
    field: str,
    setup: dict[str, Any] | None,
    *,
    n: int | None = None,
    rng: random.Random | None = None,
    rolled: dict[str, Any] | None = None,
    exclude: Iterable[Any] = (),
) -> list[str]:
    """3-5 examples for one setup field, drawn for this call."""
    kind = SETUP_FIELD_KINDS.get(field)
    if not kind:
        return []
    rng = rng or random.Random()
    ctx = setup_context(setup)
    if rolled:
        ctx["rolled"] = dict(rolled)
    current = (setup or {}).get(field) if isinstance(setup, dict) else None
    excluded = list(exclude or ())
    if isinstance(current, str) and current.strip():
        excluded.append(current)
    count = n if n is not None else rng.randint(3, 5)
    if kind in ("player_sex", "previous_life_sex"):
        count = 3
    return draw(kind, ctx, count, rng, excluded)


# ---------------------------------------------------------------------------
# Used names: name_ledger, NPCs, the player, recent player names
# ---------------------------------------------------------------------------

PLAYER_NAME_HISTORY_KEEP = 24


def ensure_tables(conn) -> None:
    # Not a campaign table: it is not cleared on a new game and not exported,
    # because its whole job is to remember the games before this one.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_name_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def remember_player_name(conn, name: str) -> None:
    name = str(name or "").strip()
    if not name or _norm(name) in {"wanderer", "player"}:
        return
    try:
        ensure_tables(conn)
        conn.execute("DELETE FROM player_name_history WHERE name = ? COLLATE NOCASE", (name,))
        conn.execute("INSERT INTO player_name_history (name) VALUES (?)", (name,))
        conn.execute(
            "DELETE FROM player_name_history WHERE id NOT IN "
            "(SELECT id FROM player_name_history ORDER BY id DESC LIMIT ?)",
            (PLAYER_NAME_HISTORY_KEEP,),
        )
    except Exception:
        pass


def recent_player_names(conn=None, limit: int = 12) -> list[str]:
    """Player names from recent games, newest first, plus the current player's."""
    own = conn is None
    try:
        if own:
            from app.db import connect

            conn = connect()
        out: list[str] = []
        try:
            row = conn.execute("SELECT name FROM player WHERE id = 1").fetchone()
            if row and row[0]:
                out.append(str(row[0]))
        except Exception:
            pass
        try:
            ensure_tables(conn)
            rows = conn.execute(
                "SELECT name FROM player_name_history ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
            out += [str(r[0]) for r in rows if r and r[0]]
        except Exception:
            pass
        seen: set[str] = set()
        unique = []
        for name in out:
            if _norm(name) not in seen and _norm(name) not in {"wanderer", "player"}:
                seen.add(_norm(name))
                unique.append(name)
        return unique[:limit]
    except Exception:
        return []
    finally:
        if own and conn is not None:
            try:
                conn.commit()
                conn.close()
            except Exception:
                pass


def record_npc_name(conn, code: str, name: str, *, turn: int = 0) -> None:
    """Write a created NPC's name to name_ledger so it is never drawn again here."""
    if not name:
        return
    try:
        from app.naming import ledger_record

        ledger_record(conn, f"npc:{code or _norm(name)}", str(name), source="npc_created", turn=int(turn or 0))
    except Exception:
        pass


def used_names(conn) -> list[str]:
    """Every person name this world has used: NPCs, name_ledger, the player."""
    names: list[str] = []
    for sql in (
        "SELECT name FROM npcs",
        "SELECT name FROM name_ledger",
        "SELECT name FROM player",
        "SELECT public_name FROM player",
    ):
        try:
            names += [str(r[0]) for r in conn.execute(sql).fetchall() if r and r[0]]
        except Exception:
            continue
    return names


def world_options(conn) -> dict[str, Any]:
    """This world's playthrough_options, or {} before Start."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
    except Exception:
        return {}
    if not row or not row[0]:
        return {}
    try:
        import json

        value = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def engine_person_name(
    conn,
    seed: Any,
    *,
    family: bool = False,
    sex: str = "",
    exclude: Iterable[Any] = (),
) -> str:
    """One name the engine gives a person it makes itself (shell NPCs, local cast, rulers).

    Drawn from this world's naming culture, never a name or name part already
    used here (NPCs, name_ledger, the player, recent player names, places).
    Deterministic for a seed and the same table contents. '' when the pool
    for this culture is used up.
    """
    try:
        ctx = world_context(world_options(conn), sex=sex)
        used = used_names(conn) + recent_player_names(conn) + used_place_names(conn) + list(exclude or ())
        names = draw_names(ctx, 1, random.Random(str(seed)), used, sex=sex, family=family)
    except Exception:
        return ""
    return names[0] if names else ""


def used_roles(conn) -> list[str]:
    try:
        return [str(r[0]) for r in conn.execute("SELECT DISTINCT role FROM npcs").fetchall() if r and r[0]]
    except Exception:
        return []


def used_place_names(conn) -> list[str]:
    try:
        return [str(r[0]) for r in conn.execute("SELECT name FROM locations").fetchall() if r and r[0]]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Turn draft: names, jobs and venue names for this turn
# ---------------------------------------------------------------------------

CAST_OPTIONS_RULE = (
    "cast_options were drawn fresh for this turn and are not people or places yet. When the story needs "
    "a new person, give them one of cast_options.names or a name in the same style, and a job from "
    "cast_options.jobs or another that fits this place. A new building may take one of "
    "cast_options.venue_names. Use them only if the scene needs them; never give anyone a name "
    "already used in world_state."
)


# In a plotted town the buildings are plots with names of their own
# (docs/TownGrid.md 5.3): no venue names are offered and none is invited.
CAST_OPTIONS_RULE_TOWN = (
    "cast_options were drawn fresh for this turn and are not people yet. When the story needs "
    "a new person, give them one of cast_options.names or a name in the same style, and a job from "
    "cast_options.jobs or another that fits this place. Use them only if the scene needs them; never "
    "give anyone a name already used in world_state."
)


def cast_options(
    options: dict[str, Any] | None,
    location: dict[str, Any] | None,
    *,
    conn=None,
    rng: random.Random | None = None,
    n_names: int | None = None,
    n_jobs: int | None = None,
) -> dict[str, Any]:
    """Unused names, jobs that fit this place, and venue names, for one draft call."""
    rng = rng or random.Random()
    ctx = world_context(options, location=location)
    names_used: list[str] = []
    roles_used: list[str] = []
    places_used: list[str] = []
    if conn is not None:
        names_used = used_names(conn) + recent_player_names(conn)
        roles_used = used_roles(conn)
        places_used = used_place_names(conn)
    out: dict[str, Any] = {
        "names": draw_names(ctx, n_names or rng.randint(3, 5), rng, names_used),
    }
    jobs = draw("npc_role", ctx, n_jobs or rng.randint(3, 5), rng, roles_used)
    if len(jobs) < 3:
        # Every job here is taken: repeat ones are better than none.
        jobs += [j for j in draw("npc_role", ctx, 5, rng) if j not in jobs][: 3 - len(jobs)]
    out["jobs"] = jobs
    loc = location if isinstance(location, dict) else {}
    if ctx.get("size") and not loc.get("inside_venue"):
        out["venue_names"] = draw("venue_name", ctx, 3, rng, places_used + names_used)
    out["rule"] = CAST_OPTIONS_RULE
    return out


def turn_cast_options(state: dict[str, Any] | None, *, turn: int = 0) -> dict[str, Any]:
    """cast_options for the draft packet, from the world's own settings and place.

    Seeded per campaign, turn and place, so a rewind offers the same draw.
    """
    state = state if isinstance(state, dict) else {}
    options = ((state.get("settings") or {}).get("playthrough_options") or {}) if isinstance(state.get("settings"), dict) else {}
    location = state.get("current_location") if isinstance(state.get("current_location"), dict) else {}
    try:
        from app.rng import rng_for

        rng = rng_for("cast_options", turn=int(turn or 0), salt=str(location.get("code") or location.get("name") or ""))
    except Exception:
        rng = random.Random()
    try:
        from app.db import connect

        with connect() as conn:
            return cast_options(options, location, conn=conn, rng=rng)
    except Exception:
        return cast_options(options, location, rng=rng)
