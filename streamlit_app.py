import streamlit as st
import os
import json
import re
import string
from google import genai
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Tuple

# ---- Style: widen sidebar and tidy spacing ----
st.markdown("""
<style>
/* Streamlit's native sidebar is always scrollable and fixed, but we'll reserve more space for it. */
[data-testid="stSidebar"] { width: 500px; min-width: 500px; } 
@media (max-width: 1200px) { [data-testid="stSidebar"] { width: 400px; min-width: 400px; } }
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

# --- Game Data and Settings (SRD-Aligned) ---

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
    "Spycraft": ["Field Agent", "Hacker", "Interrogator", "Double Agent", "Analyst", "Random"],
}

DIFFICULTY_OPTIONS = {
    "Easy (Narrative Focus)": "DC scaling is generous (max DC 15). Combat is forgiving. Puzzles are simple.",
    "Normal (Balanced)": "Standard DC scaling (max DC 20). Balanced lethality. Moderate puzzles.",
    "Hard (Lethal)": "DC scaling is brutal (max DC 25+). Critical failures are common. High chance of character death.",
}

RACE_OPTIONS = {
    "Classic Fantasy": ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling"],
    "Post-Apocalypse": ["Human", "Mutant", "Android", "Cyborg", "Beastkin", "Ghoul"],
    "Cyberpunk": ["Human", "Cyborg", "Augmented", "Synth", "Clone"],
    "Modern Fantasy": ["Human", "Fae-touched", "Vampire", "Werewolf", "Mageborn"],
    "Horror": ["Human", "Occultist", "Touched", "Fragmented"],
    "Spycraft": ["Human"],
}

RACE_MODIFIERS = {
    "Human":        {"str_mod": 0, "dex_mod": 0, "con_mod": 0, "int_mod": 0, "wis_mod": 0, "cha_mod": 0},
    "Elf":          {"dex_mod": 1, "int_mod": 1, "con_mod": -1},
    "Dwarf":        {"con_mod": 2, "cha_mod": -1},
    "Halfling":     {"dex_mod": 1, "str_mod": -1},
    "Orc":          {"str_mod": 2, "int_mod": -1, "cha_mod": -1},
    "Tiefling":     {"cha_mod": 1, "int_mod": 1, "wis_mod": -1},

    "Mutant":       {"con_mod": 1, "str_mod": 1, "cha_mod": -1},
    "Android":      {"int_mod": 2, "wis_mod": -1},
    "Cyborg":       {"str_mod": 1, "con_mod": 1, "dex_mod": -1},
    "Beastkin":     {"dex_mod": 1, "wis_mod": 1, "int_mod": -1},
    "Ghoul":        {"con_mod": 1, "cha_mod": -2},

    "Augmented":    {"dex_mod": 1, "int_mod": 1, "wis_mod": -1},
    "Synth":        {"int_mod": 2, "cha_mod": -1},
    "Clone":        {"wis_mod": 1, "cha_mod": -1},

    "Fae-touched":  {"cha_mod": 1, "wis_mod": 1, "con_mod": -1},
    "Vampire":      {"cha_mod": 1, "str_mod": 1, "con_mod": -1},
    "Werewolf":     {"str_mod": 2, "int_mod": -1},
    "Mageborn":     {"int_mod": 2, "str_mod": -1},

    "Occultist":    {"int_mod": 1, "wis_mod": 1, "con_mod": -1},
    "Touched":      {"wis_mod": 2, "cha_mod": -1},
    "Fragmented":   {"int_mod": 1, "cha_mod": -1},
}

# --- SRD equipment database (Lite) ---
SRD_ITEMS = {
    "dagger":           {"type":"weapon","hands":1,"damage":"1d4","properties":["finesse","light","thrown"]},
    "shortsword":       {"type":"weapon","hands":1,"damage":"1d6","properties":["finesse","light"]},
    "longsword":        {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "rapier":           {"type":"weapon","hands":1,"damage":"1d8","properties":["finesse"]},
    "battleaxe":        {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "warhammer":        {"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"]},
    "greataxe":         {"type":"weapon","hands":2,"damage":"1d12","properties":["heavy","two-handed"]},
    "greatsword":       {"type":"weapon","hands":2,"damage":"2d6","properties":["heavy","two-handed"]},
    "shortbow":         {"type":"weapon","hands":2,"damage":"1d6","properties":["two-handed","ammunition","range"]},
    "longbow":          {"type":"weapon","hands":2,"damage":"1d8","properties":["heavy","two-handed","ammunition","range"]},
    "shield":           {"type":"shield","hands":1,"ac_bonus":2,"properties":["worn in one arm"]},
    "leather armor":    {"type":"armor","hands":0,"armor":{"category":"light","base":11,"dex_cap":None}},
    "studded leather":  {"type":"armor","hands":0,"armor":{"category":"light","base":12,"dex_cap":None}},
    "chain shirt":      {"type":"armor","hands":0,"armor":{"category":"medium","base":13,"dex_cap":2}},
    "scale mail":       {"type":"armor","hands":0,"armor":{"category":"medium","base":14,"dex_cap":2}},
    "half plate":       {"type":"armor","hands":0,"armor":{"category":"medium","base":15,"dex_cap":2}},
    "chain mail":       {"type":"armor","hands":0,"armor":{"category":"heavy","base":16,"dex_cap":0}},
    "splint":           {"type":"armor","hands":0,"armor":{"category":"heavy","base":17,"dex_cap":0}},
    "plate":            {"type":"armor","hands":0,"armor":{"category":"heavy","base":18,"dex_cap":0}},
    "boots":            {"type":"gear","hands":0,"properties":["footwear"]},
    "cloak":            {"type":"gear","hands":0,"properties":["clothing"]},
    "ring":             {"type":"gear","hands":0,"properties":["jewelry"]},
    "amulet":           {"type":"gear","hands":0,"properties":["neckwear"]},
    "helm":             {"type":"gear","hands":0,"properties":["headwear"]},
}

SRD_ALIASES = {
    "leather": "leather armor", "leather armour": "leather armor", "studded leather armor": "studded leather",
    "studded armour": "studded leather", "chainmail": "chain mail", "chain mail armor": "chain mail",
    "chainmail armor": "chain mail", "mail": "chain mail", "half-plate": "half plate", "breastplate": "scale mail",
    "long sword": "longsword", "short sword": "shortsword", "battle axe": "battleaxe", "war hammer": "warhammer",
    "great sword": "greatsword", "great axe": "greataxe", "buckler": "shield", "helmet": "helm",
    "chain shirt armor": "chain shirt",
}

CLEAN_WORDS_TO_DROP = set(["well-made","fine","sturdy","rusty","old","new","decorated","engraved","masterwork","+1","+2","+3","+4","+5","armor","armour","of","the"])

WIZARD_SPELLS_L1 = ["Magic Missile", "Shield", "Mage Armor", "Thunderwave", "Chromatic Orb", "Grease", "Burning Hands", "Sleep", "Detect Magic", "Identify"]
CLERIC_SPELLS_L1 = ["Cure Wounds", "Bless", "Shield of Faith", "Guiding Bolt", "Healing Word", "Detect Evil and Good", "Sanctuary", "Inflict Wounds", "Protection from Evil and Good"]

CLASS_SPELL_LISTS = {"Wizard": {"1": WIZARD_SPELLS_L1}, "Cleric": {"1": CLERIC_SPELLS_L1}}
CLASS_SLOT_RULES = {"Wizard": {"1": 2}, "Cleric": {"1": 2}}

CASTER_KEYWORDS = {"wizard": "Wizard", "cleric": "Cleric"}

# --- Equipment and Stats Logic ---

SLOTS = ["right_arm", "left_arm", "body", "feet", "right_hand", "left_hand", "neck", "head"]
SLOT_LABEL = {"right_arm": "Right Arm", "left_arm": "Left Arm", "body": "Body", "feet": "Feet", "right_hand": "Right Hand", "left_hand": "Left Hand", "neck": "Neck", "head": "Head"}

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
        cap = a.get("dex_cap")
        dex_text = "+ Dex" if cap is None else (f"+ Dex (max {cap})" if cap>0 else "")
        return f"{label} — {cat} armor, AC {base}{(' ' + dex_text) if dex_text else ''}"
    props = ", ".join(stats.get("properties", [])) or "—"
    return f"{label} — {props}"

def ensure_equipped_slots(char: dict):
    if "equipped" not in char or not isinstance(char["equipped"], dict): char["equipped"] = {}
    for s in SLOTS:
        if char["equipped"].get(s) is not None and not isinstance(char["equipped"][s], dict): char["equipped"][s] = None
        char["equipped"].setdefault(s, None)

def unequip_slot(char: dict, slot: str):
    ensure_equipped_slots(char)
    char["equipped"][slot] = None

def equip_to_slot(char: dict, slot: str, item_name: str):
    ensure_equipped_slots(char)
    stats = lookup_item_stats(item_name)
    norm = (canonicalize_item_name(item_name) or item_name).lower()
    for s in SLOTS: # Unequip duplicate items
        eqs = char["equipped"].get(s)
        if eqs:
            other_norm = (canonicalize_item_name(eqs.get("item","")) or eqs.get("item","")).lower()
            if other_norm == norm: char["equipped"][s] = None
    entry = {"item": item_name, "stats": stats or {}, "summary": summarize_item(item_name, stats or {})}
    char["equipped"][slot] = entry
    # Handle two-handed weapons
    if stats and stats.get("type")=="weapon" and stats.get("hands",1) == 2:
        other = "left_arm" if slot=="right_arm" else "right_arm"
        char["equipped"][other] = entry
        for s in ["left_arm","right_arm"]:
            e = char["equipped"].get(s)
            if e and e.get("stats",{}).get("type")=="shield" and e is not entry: char["equipped"][s] = None

def auto_equip_defaults(char: dict):
    ensure_equipped_slots(char)
    inv = char.get("inventory", []) or []
    def first_srd_match(candidate_keys: List[str]) -> Optional[str]:
        for raw in inv:
            canon = canonicalize_item_name(raw)
            if canon in candidate_keys: return raw
        return None
    # Auto-equip logic (armor, main weapon, shield, etc.) remains here...
    if not char["equipped"]["body"]:
        order = ["plate","splint","chain mail","half plate","scale mail","chain shirt","studded leather","leather armor"]
        raw = first_srd_match(order)
        if raw: equip_to_slot(char,"body",raw)
    if not char["equipped"]["right_arm"]:
        chosen = None
        for raw in inv:
            st_ = lookup_item_stats(raw)
            if st_ and st_.get("type")=="weapon": chosen = raw; break
        if chosen: equip_to_slot(char,"right_arm", chosen)
    right = char["equipped"]["right_arm"]
    right_two_handed = bool(right and right.get("stats",{}).get("type")=="weapon" and right["stats"].get("hands",1)==2)
    if not right_two_handed and not char["equipped"]["left_arm"]:
        sh_raw = None
        for raw in inv:
            st_ = lookup_item_stats(raw)
            if st_ and st_.get("type")=="shield": sh_raw = raw; break
        if sh_raw: equip_to_slot(char, "left_arm", sh_raw)
    # ... (other equipment slots logic omitted for brevity, assumed to be here)

def normalize_all_equipped(char: dict):
    ensure_equipped_slots(char)
    for s in SLOTS:
        if char["equipped"].get(s):
            char["equipped"][s] = {"item": char["equipped"][s].get("item", ""), "stats": char["equipped"][s].get("stats") or lookup_item_stats(char["equipped"][s].get("item", "")) or {}, "summary": char["equipped"][s].get("summary") or summarize_item(char["equipped"][s].get("item", ""), char["equipped"][s].get("stats", {}) or {})}

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

# --- Spells and Casting Logic ---

def canonical_class(name: Optional[str]) -> str:
    s = (name or "").lower()
    for k, base in CASTER_KEYWORDS.items():
        if k in s: return base
    return (name or "").strip().title()

def get_class_spell_list(cls: str, level: int = 1) -> List[str]:
    return CLASS_SPELL_LISTS.get(cls, {}).get(str(level), [])

def initialize_spellcasting(char: dict):
    cls = canonical_class(char.get("race_class"))
    if cls not in CLASS_SPELL_LISTS:
        char.setdefault("spells_known", []); char.setdefault("spells_prepared", [])
        char.setdefault("spell_slots", {}); return

    char.setdefault("spells_known", []); char.setdefault("spells_prepared", [])
    char.setdefault("spell_slots", {})

    if "1" not in char["spell_slots"]:
        max_slots = CLASS_SLOT_RULES.get(cls, {}).get("1", 0)
        char["spell_slots"]["1"] = {"max": max_slots, "current": max_slots}

    if not char["spells_known"]:
        base_list = get_class_spell_list(cls, 1)
        char["spells_known"] = base_list[:4]

    if not char["spells_prepared"]:
        limit = 2
        if cls == "Wizard": limit = max(1, int(char.get("int_mod", 0)) + 1)
        elif cls == "Cleric": limit = max(1, int(char.get("wis_mod", 0)) + 1)
        char["spells_prepared"] = char["spells_known"][:limit]

def validate_spells_for_class(char: dict):
    cls = canonical_class(char.get("race_class"))
    class_list = set(s.lower() for s in get_class_spell_list(cls, 1))
    if not class_list:
        char["spells_known"] = []; char["spells_prepared"] = []; char["spell_slots"] = {}; return

    known = [s for s in char.get("spells_known", []) if s and s.lower() in class_list]
    if len(known) < len(char.get("spells_known", [])):
        originals = len(char.get("spells_known", []))
        pool = [x for x in get_class_spell_list(cls, 1) if x not in known]
        while len(known) < min(originals, len(get_class_spell_list(cls, 1))) and pool: known.append(pool.pop(0))
    char["spells_known"] = known

    limit = 2
    if cls == "Wizard": limit = max(1, int(char.get("int_mod", 0)) + 1)
    elif cls == "Cleric": limit = max(1, int(char.get("wis_mod", 0)) + 1)
    prepared = [s for s in char.get("spells_prepared", []) if s in known][:limit]
    if not prepared: prepared = known[:limit]
    char["spells_prepared"] = prepared

    slots = char.setdefault("spell_slots", {})
    if "1" not in slots:
        max_slots = CLASS_SLOT_RULES.get(cls, {}).get("1", 0)
        slots["1"] = {"max": max_slots, "current": max_slots}
    else:
        s = slots["1"]
        s["max"] = CLASS_SLOT_RULES.get(cls, {}).get("1", s.get("max", 0))
        s["current"] = max(0, min(s.get("current", s["max"]), s["max"]))

def cast_spell(char: dict, spell_name: str) -> bool:
    if spell_name not in char.get("spells_prepared", []): return False
    slots = char.get("spell_slots", {}).get("1")
    if not slots or slots["current"] <= 0: return False
    slots["current"] -= 1
    return True

def apply_race_modifiers(char_data: dict, race: str):
    mods = RACE_MODIFIERS.get(race, {})
    for k, delta in mods.items():
        char_data[k] = char_data.get(k, 0) + delta

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

def safe_model_text(resp) -> str:
    try:
        if hasattr(resp,"text") and resp.text and resp.text.strip(): return resp.text.strip()
        if hasattr(resp,"candidates") and resp.candidates:
            for c in resp.candidates:
                if hasattr(c,"content") and getattr(c.content,"parts",None):
                    for p in c.content.parts:
                        if getattr(p,"text",None) and p.text.strip(): return p.text.strip()
        if hasattr(resp,"prompt_feedback") and getattr(resp.prompt_feedback,"block_reason",None):
            return f"(Model returned no text; block_reason={resp.prompt_feedback.block_reason})"
    except Exception: pass
    return "(No model text returned.)"

def consume_action_and_narrate(action_text: str):
    st.session_state["history"].append({"role": "user", "content": action_text})
    try:
        final_narrative_config = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"])
        narr_resp = client.models.generate_content(model='gemini-2.5-flash', contents=get_api_contents(st.session_state["history"]), config=final_narrative_config)
        text = safe_model_text(narr_resp)
        st.session_state["history"].append({"role": "assistant", "content": text})
    except Exception as e:
        st.session_state["history"].append({"role": "assistant", "content": f"Narrative error: {e}"})
    st.rerun()

# --- Character creation / game flow ---

def create_character_wrapper():
    """Wrapper to call the character creation function with all current state values."""
    create_new_character_handler(
        st.session_state["setup_setting"], 
        st.session_state["setup_genre"], 
        st.session_state["setup_race"],
        st.session_state["new_player_name_input_setup"],
        st.session_state["setup_class"], 
        st.session_state["custom_character_description"],
        st.session_state["setup_difficulty"]
    )

def start_adventure_handler():
    """Wrapper to call start_adventure with current settings."""
    start_adventure(st.session_state["setup_setting"], st.session_state["setup_genre"])

# --- Init session state ---
st.title("🧙 RPG Storyteller DM (SRD-Aligned)")

for key, default in [
    ("history", []), ("characters", {}), ("current_player", None),
    ("final_system_instruction", None), ("new_player_name", ""),
    ("adventure_started", False), ("saved_game_json", ""),
    ("__LOAD_FLAG__", False), ("__LOAD_DATA__", None),
    ("page", "SETUP"), ("custom_setting_description", ""),
    ("custom_character_description", ""), ("new_player_name_input_setup_value", ""),
    ("setup_race", None), ("setup_class", None), ("setup_difficulty", "Normal (Balanced)"),
    ("setup_setting", "Classic Fantasy"), ("setup_genre", "High Magic Quest")
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
        
        race_choices = RACE_OPTIONS.get(st.session_state["setup_setting"], ["Human"])
        _ = st.selectbox("Choose Race", race_choices, key="setup_race")
        
        new_player_name = st.text_input("Character Name", value=st.session_state["new_player_name_input_setup_value"], key="new_player_name_input_setup")
        
        if st.session_state["characters"]:
            st.markdown(f"**Party Roster ({len(st.session_state['characters'])}):**")
            st.markdown(f"{', '.join(st.session_state['characters'].keys())}")
        
    with col_char_details:
        st.subheader("Character Description")
        st.markdown("Provide physical, personality, background, and association details (optional).")
        st.session_state["custom_character_description"] = st.text_area(
            "Character Details", 
            value=st.session_state["custom_character_description"], 
            height=150, 
            placeholder="Example: A tall, paranoid ex-corporate security guard with a visible cybernetic eye and a strong fear of heights."
        )

    if col_char_creation.button("Add Character to Party"):
        if st.session_state["new_player_name_input_setup"]:
            create_character_wrapper()
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
# PAGE 2: GAME VIEW (Main Application)
# =========================================================================

elif st.session_state["page"] == "GAME":
    
    # --- Define the two main columns (Chat + Stats/Spells) ---
    col_chat, col_stats = st.columns([5, 3]) 
    game_started = st.session_state["adventure_started"]

    # ---------------------------------------------------------------------
    # NATIVE STREAMLIT SIDEBAR (Controls - FIXED/SCROLLABLE)
    # ---------------------------------------------------------------------
    with st.sidebar:
        st.header("Game Controls")
        
        with st.expander("World & Difficulty", expanded=False):
            st.info(f"**Setting:** {st.session_state.get('setup_setting')} / {st.session_state.get('setup_genre')}")
            st.info(f"**Difficulty:** {st.session_state.get('setup_difficulty')}")
            st.markdown(f"**World Details:** {st.session_state.get('custom_setting_description')}")
        
        st.markdown("---")
        st.subheader("Save/Load")
        
        if st.button("💾 Save Adventure", disabled=not game_started, on_click=save_game): pass 
        if st.session_state["saved_game_json"]:
            st.download_button("Download Game File", st.session_state["saved_game_json"],
                               file_name="gemini_rpg_save.json", mime="application/json")
    # ---------------------------------------------------------------------

    # =========================================================================
    # RIGHT COLUMN (Active Player Stats, Equipment, and Spells)
    # =========================================================================
    with col_stats:
        active_char = st.session_state["characters"].get(st.session_state["current_player"])
        
        if active_char:
            ensure_equipped_slots(active_char)
            normalize_all_equipped(active_char)
            initialize_or_validate_spells(active_char)
            active_char['race_class'] = canonical_class(active_char.get('race_class'))

            ac_val, ac_src = compute_ac(active_char)
            
            # --- Primary Character Info (Top Bar) ---
            st.header(f"{active_char.get('name','')} ({active_char.get('race_class','')})")
            st.caption(f"Race: {active_char.get('race', '')}")

            c1, c2, c3 = st.columns(3)
            c1.metric("HP", active_char.get('current_hp', 0))
            c2.metric("AC", ac_val, help=ac_src)
            c3.metric("Sanity", active_char.get('morale_sanity', 100))

            # --- Ability Scores ---
            with st.expander("Ability Modifiers", expanded=True):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**STR**: {active_char.get('str_mod', 0)}")
                c2.markdown(f"**DEX**: {active_char.get('dex_mod', 0)}")
                c3.markdown(f"**CON**: {active_char.get('con_mod', 0)}")
                c4,c5,c6 = st.columns(3)
                c4.markdown(f"**INT**: {active_char.get('int_mod', 0)}")
                c5.markdown(f"**WIS**: {active_char.get('wis_mod', 0)}")
                c6.markdown(f"**CHA**: {active_char.get('cha_mod', 0)}")
            
            # --- Spellcasting ---
            cls = canonical_class(active_char.get("race_class"))
            class_spell_list = get_class_spell_list(cls, 1)
            if class_spell_list:
                with st.expander("Spellcasting (Lv1)", expanded=False):
                    slots = active_char["spell_slots"]["1"]
                    st.markdown(f"**Slots:** {slots['current']}/{slots['max']}")
                    
                    # Casting UI
                    cA, cB = st.columns([3,1])
                    with cA:
                        cast_choice = st.selectbox("Cast spell", options=["—"] + active_char["spells_prepared"], key=f"cast_sel_{active_char['name']}")
                    with cB:
                        if st.button("Cast", key=f"cast_btn_{active_char['name']}"):
                            if cast_choice and cast_choice != "—":
                                if cast_spell(active_char, cast_choice):
                                    consume_action_and_narrate(f"({active_char['name']}) casts {cast_choice}. Expend one level-1 spell slot.")
                                else:
                                    st.error("Cannot cast: not prepared or no slots remaining.")
                    
                    # Manage known spells (UI intensive)
                    with st.expander("Manage Known & Prepared", expanded=False):
                        new_known = st.multiselect("Known Spells", options=class_spell_list, default=[s for s in active_char["spells_known"] if s in class_spell_list], key=f"known_{active_char['name']}")
                        limit = max(1, int(active_char.get("int_mod", 0)) + 1 if cls=="Wizard" else int(active_char.get("wis_mod", 0)) + 1)
                        new_prepped = st.multiselect(f"Prepared Spells (max {limit})", options=new_known, default=[s for s in active_char["spells_prepared"] if s in new_known][:limit], key=f"prep_{active_char['name']}")
                        if st.button("Save Spells", key=f"save_spells_{active_char['name']}"):
                            active_char["spells_known"] = new_known
                            active_char["spells_prepared"] = new_prepped[:limit]
                            validate_spells_for_class(active_char)
                            st.success("Spells updated.")

            # --- Equipment ---
            with st.expander("Equipment Slots", expanded=True):
                st.markdown("**Equipped (by slot):**")
                for s in SLOTS:
                    eq = active_char["equipped"].get(s)
                    label = SLOT_LABEL[s]
                    if eq:
                        _summary = eq.get("summary") or summarize_item(eq.get("item",""), eq.get("stats", {}))
                        st.markdown(f"- **{label}:** {_summary}")
                    else:
                        st.markdown(f"- **{label}:** —")
                
                # Simple Equip/Unequip UI (Only shows if there's inventory)
                inventory_list = [item for item in active_char.get("inventory", []) if item not in [e.get("item", "") for e in active_char["equipped"].values() if e]]
                if inventory_list:
                    st.markdown("---")
                    item_to_equip = st.selectbox("Item to Equip", options=["—"] + inventory_list, key=f"equip_item_{active_char['name']}")
                    if item_to_equip != "—":
                        candidates = detect_candidate_slots(item_to_equip)
                        slot_choice = st.selectbox("Slot", [SLOT_LABEL[s] for s in candidates], key=f"equip_slot_{active_char['name']}")
                        slot_key = {v:k for k,v in SLOT_LABEL.items()}[slot_choice]
                        
                        if st.button("Equip Selected", key=f"equip_final_{active_char['name']}"):
                            equip_to_slot(active_char, slot_key, item_to_equip)
                            st.rerun()
        else:
            st.write("No active character selected.")


    # =========================================================================
    # LEFT COLUMN (Game Chat - FILLS MOST OF THE SCREEN)
    # =========================================================================
    with col_chat:
        st.header("The Story Log")
        
        # Display the conversation history in reverse order (newest on top)
        for message in reversed(st.session_state["history"]):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # =========================================================================
    # GLOBAL INPUT BOX (Fixed to the bottom of the page structure)
    # =========================================================================
    if game_started:
        prompt = st.chat_input("What do you do?")

        if prompt:
            current_player_name = st.session_state["current_player"]
            active_char = st.session_state["characters"].get(current_player_name)
            
            full_prompt = f"({current_player_name}'s Turn): {prompt}"
            st.session_state["history"].append({"role": "user", "content": full_prompt})
            
            with st.spinner("The DM is thinking..."):
                final_response_text = ""
                final_narrative_config = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"])
                raw_roll = extract_roll(prompt)

                # --- A) LOGIC CHECK (IF A ROLL IS DETECTED) ---
                if raw_roll is not None:
                    logic_prompt = f"""
                    RESOLVE A PLAYER ACTION:
                    1. Character Stats (JSON): {json.dumps(active_char)}
                    2. Equipped (by slot): {json.dumps({SLOT_LABEL[s]: active_char["equipped"][s] for s in SLOTS if active_char["equipped"].get(s)})}
                    3. Derived: Armor Class = {compute_ac(active_char)[0]}; Caster: {short_spellline(active_char)}
                    4. Player Action: "{prompt}"
                    5. Task: Determine the appropriate attribute and DC (10-20), adjusted by Difficulty. Apply SRD rules (finesse, two-handed, slots).
                    6. Calculate result (Roll {raw_roll} + Mod). Consume spell slot if necessary.
                    7. Return ONLY the SkillCheckResolution JSON.
                    """
                    
                    try:
                        logic_cfg = GenerateContentConfig(system_instruction=st.session_state["final_system_instruction"], response_mime_type="application/json", response_schema=SkillCheckResolution)
                        lresp = client.models.generate_content(model='gemini-2.5-flash', contents=logic_prompt, config=logic_cfg)
                        skill_check_outcome = json.loads(lresp.text)
                        
                        # Display mechanical box
                        roll = skill_check_outcome.get('player_d20_roll', 'N/A'); mod = skill_check_outcome.get('attribute_modifier', 'N/A')
                        total = skill_check_outcome.get('total_roll', 'N/A'); dc = skill_check_outcome.get('difficulty_class', 'N/A')
                        
                        combat_display = f"""
                        <div style='border: 2px solid green; padding: 10px; border-radius: 8px; background-color: #333333; color: white;'>
                        **{skill_check_outcome['outcome_result'].upper()}!** ({skill_check_outcome['attribute_used']} Check)
                        <hr style='border-top: 1px solid #555555; margin: 5px 0;'>
                        **Roll:** {roll} + **Mod:** {mod} = **{total}** (vs **DC:** {dc})
                        </div>
                        """
                        st.session_state["history"].append({"role": "assistant", "content": combat_display}) # Add mechanics to history
                        
                        # Prepare follow-up prompt
                        follow_up_prompt = f"""
                        The player {current_player_name}'s risky action was RESOLVED. The EXACT JSON outcome was: {json.dumps(skill_check_outcome)}.
                        1. Narrate the vivid, descriptive consequence of this result (Success/Failure).
                        2. Update the scene and ask the player what they do next.
                        """
                        
                        st.session_state["history"].append({"role": "user", "content": follow_up_prompt})

                    except Exception as e:
                        st.error(f"Logic Call Failed: {e}")
                        st.session_state["history"].pop() # Remove user prompt
                
                # --- B) NARRATIVE CALL (ALWAYS RUNS) ---
                try:
                    narrative_response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=get_api_contents(st.session_state["history"]),
                        config=final_narrative_config
                    )
                    final_response_text = safe_model_text(narrative_response)
                    
                except Exception as e:
                    final_response_text = f"Narrative API Error: {e}"

                # 3. Update history with the DM's final response
                if not final_response_text.startswith("Narrative API Error"):
                    st.session_state["history"].append({"role": "assistant", "content": final_response_text})
                
                st.rerun()
