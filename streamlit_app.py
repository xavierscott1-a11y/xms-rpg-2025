import streamlit as st
st.set_page_config(layout="wide")

import json
import re
import string
from google import genai
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Tuple
import streamlit.components.v1 as components  # NEW: for scroll-to-top

# ---- Style: widen sidebar and tidy spacing ----
st.markdown("""
<style>
[data-testid="stSidebar"] { width: 520px; min-width: 520px; } /* wider sidebar */
@media (max-width: 1200px) { [data-testid="stSidebar"] { width: 440px; min-width: 440px; } }
section[aria-label="Active Player"] div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.25rem; }
div.continue-bar { margin-top: 0.5rem; }
small.srd-note { opacity: 0.75; display:block; margin-top:1rem; }
</style>
""", unsafe_allow_html=True)

# --- Configuration (API Client Setup) ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("API Key not found. Please ensure 'GEMINI_API_KEY' is set in Streamlit Secrets.")
    st.stop()

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Error initializing Gemini Client: {e}")
    st.stop()

# --- Game Data and Settings ---

SETTINGS_OPTIONS = {
    "Classic Fantasy": ["High Magic Quest", "Gritty Dungeon Crawl", "Political Intrigue"],
    "Post-Apocalypse": ["Mutant Survival", "Cybernetic Wasteland", "Resource Scarcity"],
    "Cyberpunk": ["Corporate Espionage", "Street Gang Warfare", "AI Revolution"],
    "Modern Fantasy": ["Urban Occult Detective", "Hidden Magic Conspiracy", "Campus Supernatural Drama"],
    "Horror": ["Cosmic Dread (Lovecraftian)", "Slasher Survival", "Gothic Vampire Intrigue"],
    "Spycraft": ["Cold War Espionage", "High-Tech Corporate Infiltration", "Shadowy Global Syndicate"],
}

CLASS_OPTIONS = {
    "Classic Fantasy": ["Fighter", "Wizard", "Rogue", "Cleric", "Barbarian", "Random"],
    "Post-Apocalypse": ["Scavenger", "Mutant", "Tech Specialist", "Warlord", "Drifter", "Random"],
    "Cyberpunk": ["Street Samurai", "Netrunner", "Corpo", "Techie", "Gang Enforcer", "Random"],
    "Modern Fantasy": ["Occult Investigator", "Urban Shaman", "Witch", "Goth Musician", "Bouncer", "Random"],
    "Horror": ["Skeptical Detective", "Paranoid Survivor", "Occultist", "Tough Veteran", "Innocent Victim", "Random"],
    "Spycraft": ["Human"],  # grounded non-caster
}

DIFFICULTY_OPTIONS = {
    "Easy (Narrative Focus)": "DC scaling is generous (max DC 15). Combat is forgiving. Puzzles are simple.",
    "Normal (Balanced)": "Standard DC scaling (max DC 20). Balanced lethality. Moderate puzzles.",
    "Hard (Lethal)": "DC scaling is brutal (max DC 25+). Critical failures are common. High chance of character death.",
}

# --- Races per setting + stat modifiers ---
RACE_OPTIONS = {
    "Classic Fantasy": ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling"],
    "Post-Apocalypse": ["Human", "Mutant", "Android", "Cyborg", "Beastkin", "Ghoul"],
    "Cyberpunk": ["Human", "Cyborg", "Augmented", "Synth", "Clone"],
    "Modern Fantasy": ["Human", "Fae-touched", "Vampire", "Werewolf", "Mageborn"],
    "Horror": ["Human", "Occultist", "Touched", "Fragmented"],
    "Spycraft": ["Human"],
}

RACE_MODIFIERS = {
    "Human":       {"str_mod": 0, "dex_mod": 0, "con_mod": 0, "int_mod": 0, "wis_mod": 0, "cha_mod": 0},
    "Elf":         {"dex_mod": 1, "int_mod": 1, "con_mod": -1},
    "Dwarf":       {"con_mod": 2, "cha_mod": -1},
    "Halfling":    {"dex_mod": 1, "str_mod": -1},
    "Orc":         {"str_mod": 2, "int_mod": -1, "cha_mod": -1},
    "Tiefling":    {"cha_mod": 1, "int_mod": 1, "wis_mod": -1},

    "Mutant":      {"con_mod": 1, "str_mod": 1, "cha_mod": -1},
    "Android":     {"int_mod": 2, "wis_mod": -1},
    "Cyborg":      {"str_mod": 1, "con_mod": 1, "dex_mod": -1},
    "Beastkin":    {"dex_mod": 1, "wis_mod": 1, "int_mod": -1},
    "Ghoul":       {"con_mod": 1, "cha_mod": -2},

    "Augmented":   {"dex_mod": 1, "int_mod": 1, "wis_mod": -1},
    "Synth":       {"int_mod": 2, "cha_mod": -1},
    "Clone":       {"wis_mod": 1, "cha_mod": -1},

    "Fae-touched": {"cha_mod": 1, "wis_mod": 1, "con_mod": -1},
    "Vampire":     {"cha_mod": 1, "str_mod": 1, "con_mod": -1},
    "Werewolf":    {"str_mod": 2, "int_mod": -1},
    "Mageborn":    {"int_mod": 2, "str_mod": -1},

    "Occultist":   {"int_mod": 1, "wis_mod": 1, "con_mod": -1},
    "Touched":     {"wis_mod": 2, "cha_mod": -1},
    "Fragmented":  {"int_mod": 1, "cha_mod": -1},
}

# --- SRD equipment database (Lite) for Classic Fantasy ---
SRD_ITEMS = {
    # Weapons
    "dagger":        {"type":"weapon","hands":1,"damage":"1d4","properties":["finesse","light","thrown"]},
    "shortsword":    {"type":"weapon","hands":1,"damage":"1d6","properties":["finesse","light"]},
    "longsword":     {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "rapier":        {"type":"weapon","hands":1,"damage":"1d8","properties":["finesse"]},
    "battleaxe":     {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "warhammer":     {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "greataxe":      {"type":"weapon","hands":2,"damage":"1d12","properties":["heavy","two-handed"]},
    "greatsword":    {"type":"weapon","hands":2,"damage":"2d6","properties":["heavy","two-handed"]},
    "shortbow":      {"type":"weapon","hands":2,"damage":"1d6","properties":["two-handed","ammunition","range"]},
    "longbow":       {"type":"weapon","hands":2,"damage":"1d8","properties":["heavy","two-handed","ammunition","range"]},
    # Shields
    "shield":        {"type":"shield","hands":1,"ac_bonus":2,"properties":["worn in one arm"]},
    # Armor
    "leather armor":   {"type":"armor","hands":0,"armor":{"category":"light","base":11,"dex_cap":None}},
    "studded leather": {"type":"armor","hands":0,"armor":{"category":"light","base":12,"dex_cap":None}},
    "chain shirt":     {"type":"armor","hands":0,"armor":{"category":"medium","base":13,"dex_cap":2}},
    "scale mail":      {"type":"armor","hands":0,"armor":{"category":"medium","base":14,"dex_cap":2}},
    "half plate":      {"type":"armor","hands":0,"armor":{"category":"medium","base":15,"dex_cap":2}},
    "chain mail":      {"type":"armor","hands":0,"armor":{"category":"heavy","base":16,"dex_cap":0}},
    "splint":          {"type":"armor","hands":0,"armor":{"category":"heavy","base":17,"dex_cap":0}},
    "plate":           {"type":"armor","hands":0,"armor":{"category":"heavy","base":18,"dex_cap":0}},
    # Flavor gear
    "boots":           {"type":"gear","hands":0,"properties":["footwear"]},
    "cloak":           {"type":"gear","hands":0,"properties":["clothing"]},
    "ring":            {"type":"gear","hands":0,"properties":["jewelry"]},
    "amulet":          {"type":"gear","hands":0,"properties":["neckwear"]},
    "helm":            {"type":"gear","hands":0,"properties":["headwear"]},
}

# ---- Canonicalization: aliases + fuzzy matching to SRD keys ----

SRD_ALIASES = {
    # Armor variants / common spellings
    "leather": "leather armor",
    "leather armour": "leather armor",
    "studded leather armor": "studded leather",
    "studded armour": "studded leather",
    "chainmail": "chain mail",
    "chain mail armor": "chain mail",
    "chainmail armor": "chain mail",
    "mail": "chain mail",
    "half-plate": "half plate",
    "breastplate": "scale mail",  # stand-in in our lite list
    # Weapons spacing/synonyms
    "long sword": "longsword",
    "short sword": "shortsword",
    "battle axe": "battleaxe",
    "war hammer": "warhammer",
    "great sword": "greatsword",
    "great axe": "greataxe",
    # Shields & misc
    "buckler": "shield",
    "helmet": "helm",
    "chain shirt armor": "chain shirt",
}

CLEAN_WORDS_TO_DROP = set([
    "well-made","fine","sturdy","rusty","old","new","decorated","engraved",
    "masterwork","+1","+2","+3","+4","+5","armor","armour","of","the"
])

def _tokenize(s: str) -> List[str]:
    s = (s or "").lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    return [w for w in s.split() if w and w not in CLEAN_WORDS_TO_DROP]

def _canonical_alias(s: str) -> Optional[str]:
    key = (s or "").strip().lower()
    return SRD_ALIASES.get(key)

def canonicalize_item_name(name: str) -> Optional[str]:
    if not name: return None
    low = name.strip().lower()
    if low in SRD_ITEMS: return low
    ali = _canonical_alias(low)
    if ali in SRD_ITEMS: return ali
    tokens = _tokenize(low)
    cleaned = " ".join(tokens)
    ali2 = _canonical_alias(cleaned)
    if ali2 in SRD_ITEMS: return ali2
    if cleaned in SRD_ITEMS: return cleaned
    best = None
    best_len = -1
    name_tokens = set(tokens)
    for key in SRD_ITEMS.keys():
        key_tokens = set(_tokenize(key))
        if key_tokens and key_tokens.issubset(name_tokens):
            if len(" ".join(key_tokens)) > best_len:
                best = key
                best_len = len(" ".join(key_tokens))
    return best

def lookup_item_stats(name: str) -> Optional[Dict]:
    if not name: return None
    canon = canonicalize_item_name(name)
    if canon and canon in SRD_ITEMS:
        return SRD_ITEMS[canon]
    return None

def summarize_item(name: str, stats: Dict) -> str:
    if not stats: return (name or "—")
    label = canonicalize_item_name(name) or name
    t = stats.get("type")
    if t == "weapon":
        props = ", ".join(stats.get("properties", [])) or "—"
        hands = stats.get("hands", 1)
        return f"{label} — {stats.get('damage')} dmg, {props}; hands: {hands}"
    if t == "shield":
        return f"{label} — +{stats.get('ac_bonus',0)} AC (shield)"
    if t == "armor":
        a = stats.get("armor", {})
        cat = a.get("category","armor")
        base = a.get("base")
        cap  = a.get("dex_cap")
        dex_text = "+ Dex" if cap is None else (f"+ Dex (max {cap})" if cap>0 else "")
        return f"{label} — {cat} armor, AC {base}{(' ' + dex_text) if dex_text else ''}"
    props = ", ".join(stats.get("properties", [])) or "—"
    return f"{label} — {props}"

# --- Schemas ---

class CharacterSheet(BaseModel):
    name: str
    race_class: str
    str_mod: int
    dex_mod: int
    con_mod: int
    int_mod: int
    wis_mod: int
    cha_mod: int
    current_hp: int
    morale_sanity: int
    inventory: List[str]
    experience: int

character_creation_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)

class SkillCheckResolution(BaseModel):
    action: str
    attribute_used: str
    difficulty_class: int
    player_d20_roll: int
    attribute_modifier: int
    total_roll: int
    outcome_result: str
    hp_change: int = 0
    consequence_narrative: str

skill_check_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=SkillCheckResolution,
)

# --- Equipment system (slots + heuristics) ---

SLOTS = [
    "right_arm",  # weapon/shield
    "left_arm",   # weapon/shield
    "body",       # armor/clothes
    "feet",       # boots
    "right_hand", # ring
    "left_hand",  # ring
    "neck",       # necklace
    "head",       # helmet/diadem
]
SLOT_LABEL = {
    "right_arm": "Right Arm",
    "left_arm": "Left Arm",
    "body": "Body",
    "feet": "Feet",
    "right_hand": "Right Hand",
    "left_hand": "Left Hand",
    "neck": "Neck",
    "head": "Head",
}

_WEAPON_WORDS = [
    "sword","dagger","axe","mace","spear","bow","crossbow","staff","club",
    "blade","hammer","rapier","longsword","shortsword","katana",
    "pistol","rifle","shotgun","smg","revolver","gun","greataxe","greatsword","longbow","shortbow"
]
_SHIELD_WORDS = ["shield","buckler"]
_ARMOR_WORDS = [
    "armor","armour","leather","studded","chain","chainmail","mail","scale","plate","half plate","splint","breastplate","brigandine","vest","robes","robe","tunic"
]
_BOOTS_WORDS = ["boots","shoes","greaves","sandals","sabatons"]
_RING_WORDS = ["ring","band","signet"]
_NECK_WORDS = ["necklace","amulet","pendant","torc"]
_HEAD_WORDS = ["helmet","helm","diadem","crown","hat","hood","cap"]

def is_match(word_list, name: str) -> bool:
    low = (name or "").lower()
    return any(w in low for w in word_list)

def detect_candidate_slots(item_name: str) -> List[str]:
    slots = []
    if is_match(_SHIELD_WORDS, item_name):    slots += ["left_arm","right_arm"]
    if is_match(_WEAPON_WORDS, item_name):    slots += ["right_arm","left_arm"]
    if is_match(_ARMOR_WORDS, item_name):     slots += ["body"]
    if is_match(_BOOTS_WORDS, item_name):     slots += ["feet"]
    if is_match(_RING_WORDS, item_name):      slots += ["right_hand","left_hand"]
    if is_match(_NECK_WORDS, item_name):      slots += ["neck"]
    if is_match(_HEAD_WORDS, item_name):      slots += ["head"]
    if not slots: slots = SLOTS.copy()
    seen = set(); ordered = []
    for s in slots:
        if s not in seen:
            seen.add(s); ordered.append(s)
    return ordered

def ensure_equipped_slots(char: dict):
    if "equipped" not in char or not isinstance(char["equipped"], dict):
        char["equipped"] = {}
    for s in SLOTS:
        if char["equipped"].get(s) is not None and not isinstance(char["equipped"][s], dict):
            char["equipped"][s] = None
        char["equipped"].setdefault(s, None)

def unequip_slot(char: dict, slot: str):
    ensure_equipped_slots(char)
    char["equipped"][slot] = None

def equip_to_slot(char: dict, slot: str, item_name: str):
    ensure_equipped_slots(char)
    stats = lookup_item_stats(item_name)
    norm = (canonicalize_item_name(item_name) or item_name).lower()
    for s in SLOTS:
        eqs = char["equipped"].get(s)
        if eqs:
            other_norm = (canonicalize_item_name(eqs.get("item","")) or eqs.get("item","")).lower()
            if other_norm == norm:
                char["equipped"][s] = None
    entry = {"item": item_name, "stats": stats or {}, "summary": summarize_item(item_name, stats or {})}
    char["equipped"][slot] = entry
    if stats and stats.get("type")=="weapon" and stats.get("hands",1) == 2:
        other = "left_arm" if slot=="right_arm" else "right_arm"
        char["equipped"][other] = entry
        for s in ["left_arm","right_arm"]:
            e = char["equipped"].get(s)
            if e and e.get("stats",{}).get("type")=="shield" and e is not entry:
                char["equipped"][s] = None

def auto_equip_defaults(char: dict):
    ensure_equipped_slots(char)
    inv = char.get("inventory", []) or []
    def first_srd_match(candidate_keys: List[str]) -> Optional[str]:
        for raw in inv:
            canon = canonicalize_item_name(raw)
            if canon in candidate_keys:
                return raw
        return None
    if not char["equipped"]["body"]:
        order = ["plate","splint","chain mail","half plate","scale mail","chain shirt","studded leather","leather armor"]
        raw = first_srd_match(order)
        if raw: equip_to_slot(char,"body",raw)
    if not char["equipped"]["right_arm"]:
        chosen = None
        for raw in inv:
            st_ = lookup_item_stats(raw)
            if st_ and st_.get("type")=="weapon":
                chosen = raw; break
        if chosen:
            equip_to_slot(char,"right_arm", chosen)
    right = char["equipped"]["right_arm"]
    right_two_handed = bool(right and right.get("stats",{}).get("type")=="weapon" and right["stats"].get("hands",1)==2)
    if not right_two_handed and not char["equipped"]["left_arm"]:
        sh_raw = None
        for raw in inv:
            st_ = lookup_item_stats(raw)
            if st_ and st_.get("type")=="shield":
                sh_raw = raw; break
        if sh_raw:
            equip_to_slot(char, "left_arm", sh_raw)
    if not char["equipped"]["feet"]:
        for raw in inv:
            can = canonicalize_item_name(raw) or ""
            if "boots" in can: equip_to_slot(char,"feet",raw); break
    if not char["equipped"]["neck"]:
        for raw in inv:
            can = canonicalize_item_name(raw) or ""
            if can in ("amulet",): equip_to_slot(char,"neck",raw); break
            if "necklace" in can or "pendant" in can or "torc" in can:
                equip_to_slot(char,"neck",raw); break
    if not char["equipped"]["head"]:
        for raw in inv:
            can = canonicalize_item_name(raw) or ""
            if can in ("helm",): equip_to_slot(char,"head",raw); break
            if "helmet" in raw.lower() or "hood" in raw.lower() or "cap" in raw.lower():
                equip_to_slot(char,"head",raw); break
    if not char["equipped"]["right_hand"]:
        for raw in inv:
            can = canonicalize_item_name(raw) or raw.lower()
            if "ring" in can: equip_to_slot(char,"right_hand",raw); break
    if not char["equipped"]["left_hand"]:
        for raw in inv:
            can = canonicalize_item_name(raw) or raw.lower()
            if "ring" in can and (not char["equipped"]["right_hand"] or (canonicalize_item_name(char["equipped"]["right_hand"]["item"]) or "").lower()!=can):
                equip_to_slot(char,"left_hand",raw); break

# -------- Normalization helpers to fix legacy saves --------
def normalize_equipped_entry(entry: dict) -> Optional[dict]:
    if not isinstance(entry, dict):
        return None
    item = entry.get("item", "")
    stats = entry.get("stats") or lookup_item_stats(item) or {}
    summary = entry.get("summary") or summarize_item(item, stats)
    return {"item": item, "stats": stats, "summary": summary}

def normalize_all_equipped(char: dict):
    ensure_equipped_slots(char)
    for s in SLOTS:
        if char["equipped"].get(s):
            char["equipped"][s] = normalize_equipped_entry(char["equipped"][s])

# --- Derived stats (AC) ---

def compute_ac(char: dict) -> Tuple[int,str]:
    dex = int(char.get("dex_mod", 0))
    base = 10
    dex_add = dex
    source = ["Base 10"]
    armor_entry = char.get("equipped",{}).get("body")
    if armor_entry and armor_entry.get("stats",{}).get("type")=="armor":
        a = armor_entry["stats"]["armor"]
        base = a["base"]
        if a["dex_cap"] is None:
            dex_add = dex
            source = [f"{(canonicalize_item_name(armor_entry['item']) or armor_entry['item']).title()} {base}", "Dex"]
        else:
            cap = a["dex_cap"]
            dex_add = max(min(dex, cap), -999)
            source = [f"{(canonicalize_item_name(armor_entry['item']) or armor_entry['item']).title()} {base}", f"Dex (max {cap})"]
    else:
        base = 10
        dex_add = dex
        source = ["Base 10", "Dex"]
    shield_bonus = 0
    for arm in ["left_arm","right_arm"]:
        e = char.get("equipped",{}).get(arm)
        if e and e.get("stats",{}).get("type")=="shield":
            shield_bonus = max(shield_bonus, int(e["stats"].get("ac_bonus",0)))
    if shield_bonus:
        source.append(f"Shield +{shield_bonus}")
    ac = base + dex_add + shield_bonus
    return ac, " + ".join(source)

# ===================== SPELLS (SRD-aligned, Lv1 only for now) =====================

# SRD-ish core spell lists (subset for demo; expand as needed)
WIZARD_SPELLS_L1 = [
    "Magic Missile", "Shield", "Mage Armor", "Thunderwave", "Chromatic Orb",
    "Grease", "Burning Hands", "Sleep", "Detect Magic", "Identify"
]
CLERIC_SPELLS_L1 = [
    "Cure Wounds", "Bless", "Shield of Faith", "Guiding Bolt", "Healing Word",
    "Detect Evil and Good", "Sanctuary", "Inflict Wounds", "Protection from Evil and Good"
]

CLASS_SPELL_LISTS = {
    "Wizard": {"1": WIZARD_SPELLS_L1},
    "Cleric": {"1": CLERIC_SPELLS_L1},
}

# Simple per-class slot model (level 1 only)
CLASS_SLOT_RULES = {
    "Wizard": {"1": 2},  # Lv1 slots
    "Cleric": {"1": 2},
}

def get_class_spell_list(cls: str, level: int = 1) -> List[str]:
    return CLASS_SPELL_LISTS.get(cls, {}).get(str(level), [])

# ---- Class canonicalization so subclasses/specializations still count as casters ----
CASTER_KEYWORDS = {
    "wizard": "Wizard",
    "cleric": "Cleric",
    # add more when you add their lists: "druid": "Druid", "sorcerer": "Sorcerer", etc.
}
def canonical_class(name: Optional[str]) -> str:
    s = (name or "").lower()
    for k, base in CASTER_KEYWORDS.items():
        if k in s:
            return base
    return (name or "").strip().title()

def initialize_spellcasting(char: dict):
    """Add spell fields if the class is a caster."""
    cls = canonical_class(char.get("race_class"))
    if cls not in CLASS_SPELL_LISTS:
        char.setdefault("spells_known", [])
        char.setdefault("spells_prepared", [])
        char.setdefault("spell_slots", {})
        return

    char.setdefault("spells_known", [])
    char.setdefault("spells_prepared", [])
    char.setdefault("spell_slots", {})

    # Initialize Lv1 slots
    if "1" not in char["spell_slots"]:
        max_slots = CLASS_SLOT_RULES.get(cls, {}).get("1", 0)
        char["spell_slots"]["1"] = {"max": max_slots, "current": max_slots}

    # If no known spells, seed a couple
    if not char["spells_known"]:
        base_list = get_class_spell_list(cls, 1)
        char["spells_known"] = base_list[:4]  # first four as a starter

    # Prepared rules:
    # Wizard: prepared <= max(1, INT_mod + 1)
    # Cleric: prepared <= max(1, WIS_mod + 1)
    if not char["spells_prepared"]:
        limit = 2
        if cls == "Wizard":
            limit = max(1, int(char.get("int_mod", 0)) + 1)
        elif cls == "Cleric":
            limit = max(1, int(char.get("wis_mod", 0)) + 1)
        char["spells_prepared"] = char["spells_known"][:limit]

def validate_spells_for_class(char: dict):
    """Strip/replace illegal spells that don't fit the character's class list."""
    cls = canonical_class(char.get("race_class"))
    class_list = set(s.lower() for s in get_class_spell_list(cls, 1))
    if not class_list:
        char["spells_known"] = []
        char["spells_prepared"] = []
        char["spell_slots"] = {}
        return

    # Normalize known
    known = []
    for s in char.get("spells_known", []):
        if s and s.lower() in class_list:
            known.append(s)
    if len(known) < len(char.get("spells_known", [])):
        # add replacements until we reach original count or exhaust class list
        originals = len(char.get("spells_known", []))
        pool = [x for x in get_class_spell_list(cls, 1) if x not in known]
        while len(known) < min(originals, len(get_class_spell_list(cls, 1))) and pool:
            known.append(pool.pop(0))
    char["spells_known"] = known

    # Prepared (subset of known); limit by class rule
    limit = 2
    if cls == "Wizard":
        limit = max(1, int(char.get("int_mod", 0)) + 1)
    elif cls == "Cleric":
        limit = max(1, int(char.get("wis_mod", 0)) + 1)
    prepared = [s for s in char.get("spells_prepared", []) if s in known][:limit]
    if not prepared:
        prepared = known[:limit]
    char["spells_prepared"] = prepared

    # Ensure slots present and clamped
    slots = char.setdefault("spell_slots", {})
    if "1" not in slots:
        max_slots = CLASS_SLOT_RULES.get(cls, {}).get("1", 0)
        slots["1"] = {"max": max_slots, "current": max_slots}
    else:
        s = slots["1"]
        s["max"] = CLASS_SLOT_RULES.get(cls, {}).get("1", s.get("max", 0))
        s["current"] = max(0, min(s.get("current", s["max"]), s["max"]))

def cast_spell(char: dict, spell_name: str) -> bool:
    """Consume a level-1 slot if available and the spell is prepared; return True if cast."""
    if spell_name not in char.get("spells_prepared", []):
        return False
    slots = char.get("spell_slots", {}).get("1")
    if not slots or slots["current"] <= 0:
        return False
    slots["current"] -= 1
    return True

def short_spellline(char: dict) -> str:
    """Compact readout for UI: slots and prepared list."""
    slots = char.get("spell_slots", {}).get("1", {"current":0,"max":0})
    prepped = ", ".join(char.get("spells_prepared", [])) or "—"
    return f"Slots (Lv1): {slots['current']}/{slots['max']} | Prepared: {prepped}"

# --- JS helper: scroll to top on next render ---

def _scroll_to_top():
    components.html(
        """
        <script>
        window.parent.scrollTo({ top: 0, behavior: 'smooth' });
        </script>
        """,
        height=0,
    )

# --- Model helpers & prompts ---

SYSTEM_INSTRUCTION_TEMPLATE = """
You are the ultimate Dungeon Master (DM) and Storyteller for {player_count} players in **{setting}, {genre}**.
IMPORTANT: Integrate the following user-provided details into the world and character backgrounds:
Setting Details: {custom_setting_description}
---
Follow SRD-aligned rules (D&D 5e SRD-style, CC-BY-4.0) while keeping narration vivid:
- Use STR for melee attack checks unless a weapon has the *finesse* property; use DEX for ranged.
- Respect equipment stats and properties provided in the context. Two-handed weapons occupy both arms; no shield simultaneously.
- Armor Class uses SRD-like formulas (light: base + Dex; medium: base + Dex up to +2; heavy: fixed; shield +2).
- Spells must be class-appropriate. Wizards cast from Wizard lists; Clerics from Cleric lists. Spell slots are limited and must be consumed when casting.
- After a skill/attack/spell resolution, include a mechanical line like:
  "(Target AC {{dc}} vs Roll {{roll}} + Mod {{mod}} = {{total}}. {{'Success' if total >= dc else 'Failure'}})"
Tone: immersive, tense, dramatic. Output pure narrative unless asked to produce JSON for checks.
"""

def get_api_contents(history_list):
    contents = []
    for msg in history_list:
        if msg.get("content") and isinstance(msg["content"], str):
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def safe_model_text(resp) -> str:
    try:
        if hasattr(resp,"text") and resp.text and resp.text.strip():
            return resp.text.strip()
        if hasattr(resp,"candidates") and resp.candidates:
            for c in resp.candidates:
                if hasattr(c,"content") and getattr(c.content,"parts",None):
                    for p in c.content.parts:
                        if getattr(p,"text",None) and p.text.strip():
                            return p.text.strip()
        if hasattr(resp,"prompt_feedback") and getattr(resp.prompt_feedback,"block_reason",None):
            return f"(Model returned no text; block_reason={resp.prompt_feedback.block_reason})"
    except Exception:
        pass
    return "(No model text returned.)"

# --- Narrative “system action” helper (consumes a turn) ---

def consume_action_and_narrate(action_text: str):
    st.session_state["history"].append({"role": "user", "content": action_text})
    try:
        final_narrative_config = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"])
        narr_resp = client.models.generate_content(model='gemini-2.5-flash',
                                                   contents=get_api_contents(st.session_state["history"]),
                                                   config=final_narrative_config)
        text = safe_model_text(narr_resp)
        st.session_state["history"].append({"role": "assistant", "content": text})
    except Exception as e:
        st.session_state["history"].append({"role": "assistant", "content": f"Narrative error: {e}"})
    # NEW: request a top scroll on the next render
    st.session_state["_scroll_to_top"] = True
    st.rerun()

# --- Character creation / game flow ---

def apply_race_modifiers(char_data: dict, race: str):
    mods = RACE_MODIFIERS.get(race, {})
    for k, delta in mods.items():
        char_data[k] = char_data.get(k, 0) + delta

def initialize_or_validate_spells(char: dict):
    initialize_spellcasting(char)
    validate_spells_for_class(char)

def create_new_character_handler(setting, genre, race, player_name, selected_class, custom_char_desc, difficulty):
    if not player_name or player_name in st.session_state["characters"]:
        st.error("Please enter a unique name for the new character.")
        return

    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=len(st.session_state["characters"]) + 1,
        custom_setting_description=st.session_state.get('custom_setting_description', "")
    )
    
    creation_prompt = f"""
    Create a starting character named {player_name} for {setting}/{genre}.
    Class: {selected_class}. Race: {race}.
    Description (player-provided): {custom_char_desc if custom_char_desc else "None provided; invent suitable flavor."}
    Constraints: attribute modifiers between -1 and +3; starting HP 20; Morale/Sanity 100; inventory 3-5 items suitable for SRD fantasy.
    Return ONLY the required JSON schema.
    """
    with st.spinner(f"Creating {player_name}..."):
        try:
            char_config = GenerateContentConfig(system_instruction=final_system_instruction,
                                                response_mime_type="application/json",
                                                response_schema=CharacterSheet)
            resp = client.models.generate_content(model='gemini-2.5-flash',
                                                  contents=creation_prompt,
                                                  config=char_config)
            raw = resp.text or ""
            if not raw.strip():
                st.error("Character creation returned no text.")
                return
            char_data = json.loads(raw)
            char_data['name'] = player_name
            char_data['race'] = race

            # Ensure numeric mods exist
            for k in ["str_mod","dex_mod","con_mod","int_mod","wis_mod","cha_mod"]:
                char_data.setdefault(k, 0)

            # Canonicalize class for spell system visibility
            char_data['race_class'] = canonical_class(char_data.get('race_class'))

            apply_race_modifiers(char_data, race)

            ensure_equipped_slots(char_data)
            auto_equip_defaults(char_data)
            normalize_all_equipped(char_data)

            # Spellcasting init & cleanup (e.g., remove Wizard-inappropriate spells like Cure Wounds)
            initialize_or_validate_spells(char_data)

            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            if not st.session_state["current_player"]:
                st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"{player_name} ({race}) joins the party."})

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}")
            st.session_state["history"].append({"role": "assistant", "content": f"Character creation error: {e}"})

    st.session_state["new_player_name_input_setup_value"] = ""
    st.session_state["custom_character_description"] = ""
    st.rerun() 

def extract_roll(text):
    m = re.search(r'\b(roll|rolls|rolled|try|trying|tries)\s+(\d{1,2})\b', text or "", re.IGNORECASE)
    if m:
        val = int(m.group(2))
        if 1 <= val <= 20: return val
    return None

def start_adventure_handler():
    start_adventure(st.session_state["setup_setting"], st.session_state["setup_genre"])

def start_adventure(setting, genre):
    if st.session_state["current_player"] is None:
        st.error("Please create at least one character before starting the adventure!")
        return
    for _n, _c in st.session_state["characters"].items():
        ensure_equipped_slots(_c); auto_equip_defaults(_c); normalize_all_equipped(_c)
        initialize_or_validate_spells(_c)
    intro_prompt = f"""
    Start a dramatic 3–4 paragraph introduction for {setting} / {genre}.
    Name the starting location; set vivid scene; present a clear inciting situation;
    end by asking {st.session_state['current_player']} what they do next.
    """
    with st.spinner("Spinning up the world..."):
        try:
            final_narrative_config = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"])
            resp = client.models.generate_content(model='gemini-2.5-flash', contents=intro_prompt, config=final_narrative_config)
            text = safe_model_text(resp)
            st.session_state["history"] = [{"role": "assistant", "content": text}]
            st.session_state["adventure_started"] = True
            st.session_state["page"] = "GAME"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to start adventure: {e}")
            st.session_state["history"].append({"role": "assistant", "content": f"Start error: {e}"})

def save_game():
    if not st.session_state["adventure_started"]:
        st.warning("Adventure must be started to save game.")
        return
    game_state = {
        "history": st.session_state["history"],
        "characters": st.session_state["characters"],
        "system_instruction": st.session_state["final_system_instruction"],
        "current_player": st.session_state["current_player"],
        "adventure_started": st.session_state["adventure_started"],
        "setting": st.session_state["setup_setting"], 
        "genre": st.session_state["setup_genre"],
        "difficulty": st.session_state["setup_difficulty"],
        "custom_setting_description": st.session_state["custom_setting_description"],
    }
    st.session_state["saved_game_json"] = json.dumps(game_state, indent=2)
    st.success("Game state saved. Use Download to save the file.")

def load_game(uploaded_file):
    if uploaded_file is not None:
        try:
            bytes_data = uploaded_file.read()
            loaded = json.loads(bytes_data)
            st.session_state["__LOAD_DATA__"] = loaded
            st.session_state["__LOAD_FLAG__"] = True
            st.success("Adventure loaded. Restarting session...")
            st.rerun()
        except Exception as e:
            st.error(f"Error loading file: {e}. Ensure valid JSON.")

# --- staged load (before widgets) ---
if "__LOAD_FLAG__" in st.session_state and st.session_state["__LOAD_FLAG__"]:
    d = st.session_state["__LOAD_DATA__"]
    st.session_state["history"] = d["history"]
    st.session_state["characters"] = d["characters"]
    st.session_state["final_system_instruction"] = d["system_instruction"]
    st.session_state["current_player"] = d["current_player"]
    st.session_state["adventure_started"] = d["adventure_started"]
    st.session_state["setup_setting"] = d.get("setting", "Post-Apocalypse")
    st.session_state["setup_genre"] = d.get("genre", "Mutant Survival")
    st.session_state["setup_difficulty"] = d.get("difficulty", "Normal (Balanced)") 
    st.session_state["custom_setting_description"] = d.get("custom_setting_description", "")
    for k, v in st.session_state["characters"].items():
        # normalize class and systems on load
        v['race_class'] = canonical_class(v.get('race_class'))
        ensure_equipped_slots(v)
        normalize_all_equipped(v)
        initialize_or_validate_spells(v)
    st.session_state["page"] = "GAME"
    st.session_state["__LOAD_FLAG__"] = False
    del st.session_state["__LOAD_DATA__"]

# --- Init session state ---
st.title("🧙 RPG Storyteller DM (SRD-Aligned)")

for key, default in [
    ("history", []), ("characters", {}), ("current_player", None),
    ("final_system_instruction", None), ("new_player_name", ""),
    ("adventure_started", False), ("saved_game_json", ""),
    ("__LOAD_FLAG__", False), ("__LOAD_DATA__", None),
    ("page", "SETUP"), ("custom_setting_description", ""),
    ("custom_character_description", ""), ("new_player_name_input_setup_value", ""),
    ("setup_race", None), ("_scroll_to_top", False)  # NEW: scroll flag default
]:
    if key not in st.session_state: st.session_state[key] = default

# =========================================================================
# PAGE 1: SETUP VIEW
# =========================================================================
if st.session_state["page"] == "SETUP":
    st.header("1. Define Your Campaign World")
    col_world_settings, col_world_description = st.columns([1, 2])
    
    with col_world_settings:
        st.subheader("Core Setting")
        _ = st.selectbox("Choose Setting", list(SETTINGS_OPTIONS.keys()), key="setup_setting")
        _ = st.selectbox("Choose Genre", SETTINGS_OPTIONS[st.session_state["setup_setting"]], key="setup_genre")
        st.subheader("Difficulty")
        _ = st.selectbox("Game Difficulty", list(DIFFICULTY_OPTIONS.keys()), key="setup_difficulty")
        st.caption(DIFFICULTY_OPTIONS[st.session_state["setup_difficulty"]])
        st.markdown("---")
        st.subheader("Load Existing Game")
        uploaded_file = st.file_uploader("Load Adventure File", type="json")
        if uploaded_file is not None and st.button("Load"):
            load_game(uploaded_file)

    with col_world_description:
        st.subheader("Custom World Details")
        st.session_state["custom_setting_description"] = st.text_area(
            "Setting Details (optional)", 
            value=st.session_state["custom_setting_description"], 
            height=200, 
            placeholder="Example: The city is built inside an enormous, toxic dome. The main currency is clean air filters."
        )

    st.markdown("---")
    st.header("2. Create Your Party")

    col_char_creation, col_char_details = st.columns([1, 2])

    with col_char_creation:
        st.subheader("New Character")
        selected_class_list = CLASS_OPTIONS[st.session_state.get('setup_setting', 'Classic Fantasy')]
        _ = st.selectbox("Choose Class/Role", selected_class_list, key="setup_class")
        _ = st.text_input("Character Name", value=st.session_state["new_player_name_input_setup_value"], key="new_player_name_input_setup")
        if st.session_state["characters"]:
            st.markdown(f"**Party Roster ({len(st.session_state['characters'])}):**")
            st.markdown(f"{', '.join(st.session_state['characters'].keys())}")
        
    with col_char_details:
        st.subheader("Character Description")
        st.session_state["custom_character_description"] = st.text_area(
            "Character Details", 
            value=st.session_state["custom_character_description"], 
            height=150, 
            placeholder="Example: A tall, paranoid ex-corporate guard with a cybernetic eye and a fear of heights."
        )
        race_choices = RACE_OPTIONS.get(st.session_state["setup_setting"], ["Human"])
        st.session_state["setup_race"] = st.selectbox("Race", race_choices, index=0)

    if col_char_creation.button("Add Character to Party"):
        if st.session_state["new_player_name_input_setup"]:
            create_new_character_handler(
                st.session_state["setup_setting"], 
                st.session_state["setup_genre"],
                st.session_state["setup_race"],
                st.session_state["new_player_name_input_setup"],
                st.session_state["setup_class"],
                st.session_state["custom_character_description"],
                st.session_state["setup_difficulty"]
            )
        else:
            st.error("Please provide a Character Name.")

    st.markdown("---")
    st.header("3. Start Game")
    if st.session_state["current_player"]:
        st.success(f"Party ready! {len(st.session_state['characters'])} player(s) created.")
        st.button("🚀 START ADVENTURE", on_click=start_adventure_handler, type="primary")
    else:
        st.warning("Create at least one character to start.")

# =========================================================================
# PAGE 2: GAME VIEW
# =========================================================================
elif st.session_state["page"] == "GAME":
    # NEW: If previous action requested a top scroll, do it now and clear the flag
    if st.session_state.get("_scroll_to_top"):
        _scroll_to_top()
        st.session_state["_scroll_to_top"] = False

    col_chat = st.container()
    game_started = st.session_state["adventure_started"]

    with st.sidebar:
        with st.expander("Active Player", expanded=True):
            if st.session_state["characters"]:
                player_options = list(st.session_state["characters"].keys())
                default_index = (player_options.index(st.session_state["current_player"])
                                 if st.session_state["current_player"] in player_options else 0)

                def _on_player_change():
                    st.session_state["current_player"] = st.session_state["player_selector"]; 
                    st.session_state["_scroll_to_top"] = True  # keep UX consistent when switching
                    st.rerun()

                st.selectbox("Current Turn", player_options, key="player_selector",
                             index=default_index, disabled=not game_started, on_change=_on_player_change)

                active_char = st.session_state["characters"].get(st.session_state["current_player"])
                st.markdown("---")
                if active_char:
                    ensure_equipped_slots(active_char)
                    normalize_all_equipped(active_char)
                    # normalize class on the fly (covers old saves)
                    active_char['race_class'] = canonical_class(active_char.get('race_class'))
                    initialize_or_validate_spells(active_char)

                    ac_val, ac_src = compute_ac(active_char)
                    st.markdown(f"**Name:** {active_char.get('name','')}")
                    st.markdown(f"**Race:** {active_char.get('race','')}")
                    st.markdown(f"**Class:** {active_char.get('race_class','')}")
                    st.markdown(f"**HP:** {active_char.get('current_hp','')}")
                    st.markdown(f"**AC:** {ac_val}  \n<small>({ac_src})</small>", unsafe_allow_html=True)
                    st.markdown(f"**Sanity/Morale:** {active_char.get('morale_sanity','')}")

                    # Inventory with equip buttons
                    st.markdown("**Inventory:**")
                    if active_char.get("inventory"):
                        for idx, item in enumerate(active_char["inventory"]):
                            candidates = detect_candidate_slots(item)
                            c0, c1, c2 = st.columns([4,3,2])
                            with c0: st.markdown(f"- {item}")
                            with c1:
                                slot_choice = st.selectbox("Slot", [SLOT_LABEL[s] for s in candidates],
                                                           key=f"slot_select_{active_char['name']}_{idx}")
                            with c2:
                                slot_key = {v:k for k,v in SLOT_LABEL.items()}[slot_choice]
                                occupied = None
                                for s in SLOTS:
                                    eqs = active_char["equipped"].get(s)
                                    if eqs and (canonicalize_item_name(eqs.get("item","")) or eqs.get("item","")).lower() == (canonicalize_item_name(item) or item).lower():
                                        occupied = s; break
                                if occupied:
                                    if st.button("Unequip", key=f"inv_unequip_{active_char['name']}_{idx}"):
                                        unequip_slot(active_char, occupied)
                                        consume_action_and_narrate(f"({active_char['name']}) spends their turn unequipping {item}.")
                                else:
                                    if st.button("Equip", key=f"inv_equip_{active_char['name']}_{idx}"):
                                        equip_to_slot(active_char, slot_key, item)
                                        stats = lookup_item_stats(item) or {}
                                        if stats.get("type")=="weapon" and stats.get("hands",1)==2:
                                            consume_action_and_narrate(f"({active_char['name']}) equips {item} (two-handed) and readies themselves.")
                                        else:
                                            consume_action_and_narrate(f"({active_char['name']}) equips {item} to the {SLOT_LABEL[slot_key]}.")

                    else:
                        st.caption("— (empty)")

                    # Equipped with auto summaries
                    st.markdown("**Equipped (by slot):**")
                    for s in SLOTS:
                        eq = active_char["equipped"].get(s)
                        label = SLOT_LABEL[s]
                        if eq:
                            _summary = eq.get("summary") or summarize_item(eq.get("item",""), eq.get("stats", {}))
                            st.markdown(f"- **{label}:** {_summary}")
                        else:
                            st.markdown(f"- **{label}:** —")

                    st.markdown("---")
                    st.markdown("**Ability Modifiers**")
                    c1,c2,c3 = st.columns(3)
                    with c1: st.markdown(f"**STR**: {active_char.get('str_mod', 0)}")
                    with c2: st.markdown(f"**DEX**: {active_char.get('dex_mod', 0)}")
                    with c3: st.markdown(f"**CON**: {active_char.get('con_mod', 0)}")
                    c4,c5,c6 = st.columns(3)
                    with c4: st.markdown(f"**INT**: {active_char.get('int_mod', 0)}")
                    with c5: st.markdown(f"**WIS**: {active_char.get('wis_mod', 0)}")
                    with c6: st.markdown(f"**CHA**: {active_char.get('cha_mod', 0)}")

                    # ---------- SPELLS UI ----------
                    cls = canonical_class(active_char.get("race_class"))
                    class_spell_list = get_class_spell_list(cls, 1)
                    if class_spell_list:
                        st.markdown("---")
                        st.subheader("Spells (Level 1)")
                        slots = active_char["spell_slots"]["1"]
                        st.markdown(f"**Slots:** {slots['current']}/{slots['max']}  \n**Prepared:** {', '.join(active_char['spells_prepared']) or '—'}")

                        # Manage known spells (bounded to class list)
                        with st.expander("Manage Known & Prepared", expanded=False):
                            new_known = st.multiselect(
                                "Known Spells",
                                options=class_spell_list,
                                default=[s for s in active_char["spells_known"] if s in class_spell_list],
                                help="Choose spells your class can learn.",
                                key=f"known_{active_char['name']}"
                            )
                            # Prepared limit
                            limit = 2
                            if cls == "Wizard":
                                limit = max(1, int(active_char.get("int_mod", 0)) + 1)
                            elif cls == "Cleric":
                                limit = max(1, int(active_char.get("wis_mod", 0)) + 1)

                            new_prepped = st.multiselect(
                                f"Prepared Spells (max {limit})",
                                options=new_known,
                                default=[s for s in active_char["spells_prepared"] if s in new_known][:limit],
                                key=f"prep_{active_char['name']}"
                            )
                            if st.button("Save Spells", key=f"save_spells_{active_char['name']}"):
                                active_char["spells_known"] = new_known
                                active_char["spells_prepared"] = new_prepped[:limit]
                                validate_spells_for_class(active_char)
                                st.success("Spells updated.")

                        # Casting UI
                        cA, cB = st.columns([3,1])
                        with cA:
                            cast_choice = st.selectbox(
                                "Cast a prepared spell",
                                options=["—"] + active_char["spells_prepared"],
                                key=f"cast_sel_{active_char['name']}"
                            )
                        with cB:
                            if st.button("Cast", key=f"cast_btn_{active_char['name']}"):
                                if cast_choice and cast_choice != "—":
                                    if cast_spell(active_char, cast_choice):
                                        consume_action_and_narrate(
                                            f"({active_char['name']}) casts {cast_choice}. Expend one level-1 spell slot."
                                        )
                                    else:
                                        st.error("Cannot cast: not prepared or no slots remaining.")

            else:
                st.info("No characters created yet.")

        st.header("Game Controls")
        with st.expander("World & Difficulty", expanded=False):
            st.info(f"**Setting:** {st.session_state.get('setup_setting')} / {st.session_state.get('setup_genre')}")
            st.info(f"**Difficulty:** {st.session_state.get('setup_difficulty')}")
            st.markdown(f"**World Details:** {st.session_state.get('custom_setting_description')}")

        st.markdown("---")
        st.subheader("Save/Load")
        if st.button("💾 Save Adventure", disabled=not game_started, on_click=save_game):
            pass
        if st.session_state["saved_game_json"]:
            st.download_button("Download Game File", st.session_state["saved_game_json"],
                               file_name="gemini_rpg_save.json", mime="application/json")

        st.markdown('<small class="srd-note">This work includes material from the D&D 5.1/5.2 System Reference Documents (SRD), '
                    'licensed under CC-BY-4.0 by Wizards of the Coast. You may reuse SRD portions with proper attribution.</small>',
                    unsafe_allow_html=True)

    # ---------------------- MAIN CHAT AREA ----------------------
    with col_chat:
        st.header("The Story Log")
        for message in reversed(st.session_state["history"]):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # ---------------------- INPUT AREA ----------------------
    if game_started:
        prompt = st.chat_input("What do you do?")
        with st.container():
            st.markdown('<div class="continue-bar"></div>', unsafe_allow_html=True)
            continue_clicked = st.button("▶ Continue / Next scene")

        if (prompt is not None and prompt.strip() != "") or continue_clicked:
            current_player_name = st.session_state["current_player"]
            active_char = st.session_state["characters"].get(current_player_name)
            ensure_equipped_slots(active_char)
            normalize_all_equipped(active_char)
            active_char['race_class'] = canonical_class(active_char.get('race_class'))
            initialize_or_validate_spells(active_char)

            if prompt and prompt.strip():
                st.session_state["history"].append({"role":"user","content":f"({current_player_name}'s Turn): {prompt}"})
            else:
                st.session_state["history"].append({"role":"user","content":
                    f"({current_player_name}) asks the Storyteller to continue describing the scene or advance to the next meaningful beat."})

            with st.spinner("The DM is thinking..."):
                final_cfg = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"])
                raw_roll = extract_roll(prompt) if (prompt and prompt.strip()) else None

                # Summaries for the model
                eq_summary = {SLOT_LABEL[s]: active_char["equipped"][s] for s in SLOTS if active_char["equipped"].get(s)}
                ac_val, _ = compute_ac(active_char)
                caster_line = short_spellline(active_char)

                # Logic call only if there was a roll
                if raw_roll is not None:
                    logic_prompt = f"""
                    RESOLVE A PLAYER ACTION (SRD-style):
                    Character JSON: {json.dumps(active_char)}
                    Equipped (by slot): {json.dumps(eq_summary)}
                    Derived: Armor Class = {ac_val}; Caster: {caster_line}
                    Player Action: "{prompt}"
                    Rules:
                    - Use STR for melee unless weapon has finesse; DEX for ranged; apply properties when relevant.
                    - Respect two-handed: if weapon has "two-handed", both arms are occupied; no shield benefits.
                    - Choose a reasonable DC (10–20) and compute total = d20 roll ({raw_roll}) + the relevant ability modifier.
                    - If the action is a spellcasting attempt, ensure the spell is class-appropriate and prepared, and consume a slot.
                    Return ONLY the SkillCheckResolution JSON.
                    """
                    try:
                        logic_cfg = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"],
                                                          response_mime_type="application/json",
                                                          response_schema=SkillCheckResolution)
                        lresp = client.models.generate_content(model='gemini-2.5-flash',
                                                               contents=logic_prompt, config=logic_cfg)
                        raw = lresp.text or ""
                        if raw.strip():
                            skill = json.loads(raw)
                            roll = skill.get('player_d20_roll','N/A')
                            mod  = skill.get('attribute_modifier','N/A')
                            total= skill.get('total_roll','N/A')
                            dc   = skill.get('difficulty_class','N/A')
                            st.markdown(f"""
                            <div style="border:2px solid #2e7d32;padding:10px;border-radius:8px;background-color:#1e1e1e;color:#ffffff;">
                              <div style="font-weight:700;margin-bottom:6px;">{skill.get('outcome_result','').upper()}! ({skill.get('attribute_used','')} Check)</div>
                              <hr style="border:none;border-top:1px solid #555;margin:6px 0;">
                              <div><strong>Roll:</strong> {roll} + <strong>Mod:</strong> {mod} = <strong>{total}</strong> (vs <strong>DC:</strong> {dc})</div>
                            </div>
                            """, unsafe_allow_html=True)
                            st.toast(f"Result: {skill.get('outcome_result','')}")
                            follow_up = f"""
                            The player's risky action was resolved. EXACT JSON outcome: {json.dumps(skill)}.
                            1) Narrate vivid consequences consistent with SRD gear/properties and AC.
                            2) If a spell was involved, ensure it was class-appropriate and slots are respected.
                            3) Ask what the player does next.
                            """
                            st.session_state["history"].append({"role":"assistant","content":f"//Mechanics: {json.dumps(skill)}//"})
                            st.session_state["history"].append({"role":"user","content": follow_up})
                        else:
                            st.session_state["history"].append({"role":"assistant","content":"(No JSON from logic call.)"})
                    except Exception as e:
                        st.session_state["history"].append({"role":"assistant","content":f"Logic error: {e}"})

                # Narrative call (always)
                try:
                    nresp = client.models.generate_content(model='gemini-2.5-flash',
                                                           contents=get_api_contents(st.session_state["history"]),
                                                           config=final_cfg)
                    st.session_state["history"].append({"role":"assistant","content": safe_model_text(nresp)})
                except Exception as e:
                    st.session_state["history"].append({"role":"assistant","content": f"Narrative error: {e}"})
                # NEW: request top scroll, then rerun
                st.session_state["_scroll_to_top"] = True
                st.rerun()

# End of file
