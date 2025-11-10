import streamlit as st
import os
import json
import re
import string
from google import genai
# Necessary imports for structured data and content types
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field # <--- CORRECTED IMPORT
from typing import List, Dict, Optional, Tuple # Ensure all typing helpers are present

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

# WRAPPER FOR START ADVENTURE BUTTON (Corrected function call)
def start_adventure_handler():
    """Wrapper to call start_adventure with current settings."""
    start_adventure(st.session_state["setup_setting"], st.session_state["setup_genre"])


# WRAPPER FOR ADD CHARACTER BUTTON
def create_character_wrapper():
    """Wrapper to call the character creation function with all current state values."""
    create_new_character_handler(
        st.session_state["setup_setting"], 
        st.session_state["setup_genre"], 
        st.session_state["setup_race"], # Corrected argument order
        st.session_state["new_player_name_input_setup"],
        st.session_state["setup_class"], 
        st.session_state["custom_character_description"],
        st.session_state["setup_difficulty"]
    )

def create_new_character_handler(setting, genre, race, player_name, selected_class, custom_char_desc, difficulty):
    """Function to call the API and create a character JSON."""
    
    if not player_name or player_name in st.session_state["characters"]:
        st.error("Please enter a unique name for the new character.")
        return

    # 1. Update the System Instruction with the user's choices
    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=len(st.session_state["characters"]) + 1,
        custom_setting_description=st.session_state['custom_setting_description'],
        difficulty_level=difficulty,
        difficulty_rules=DIFFICULTY_OPTIONS[difficulty]
    )
    
    creation_prompt = f"""
    Create a starting character named {player_name} for {setting}/{genre}.
    Class: {selected_class}. Race: {race}.
    Description (player-provided): {custom_char_desc if custom_char_desc else "None provided; invent suitable flavor."}
    Constraints: attribute modifiers between -1 and +3; starting HP 20; Morale/Sanity 100; inventory 3-5 items suitable for SRD fantasy.
    Return ONLY the required JSON schema.
    """
    
    with st.spinner(f"Creating survivor {player_name} for {genre}..."):
        try:
            temp_config = GenerateContentConfig(system_instruction=final_system_instruction,
                                                response_mime_type="application/json",
                                                response_schema=CharacterSheet)
            
            resp = client.models.generate_content(model='gemini-2.5-flash',
                                                contents=creation_prompt,
                                                config=temp_config)
            raw = resp.text or ""
            if not raw.strip():
                st.error("Character creation returned no text.")
                return
            char_data = json.loads(raw)
            char_data['name'] = player_name
            char_data['race'] = race

            for k in ["str_mod","dex_mod","con_mod","int_mod","wis_mod","cha_mod"]: char_data.setdefault(k, 0)
            char_data['race_class'] = canonical_class(char_data.get('race_class'))
            apply_race_modifiers(char_data, race)

            ensure_equipped_slots(char_data)
            auto_equip_defaults(char_data)
            normalize_all_equipped(char_data)

            initialize_or_validate_spells(char_data)

            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            if not st.session_state["current_player"]:
                st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"Player {player_name} added to the party. Ready for adventure initiation."})

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}. Try again in a moment.")
            st.session_state["history"].append({"role": "assistant", "content": "Failed to create character due to API error. Please try again."})

    # --- FINAL CLEANUP AND RERUN ---
    st.session_state["new_player_name_input_setup_value"] = ""
    st.session_state["custom_character_description"] = ""
    st.rerun() 


def start_adventure(setting, genre):
    """Function to generate the initial narrative hook."""
    if st.session_state["current_player"] is None:
        st.error("Please create at least one character before starting the adventure!")
        return
        
    intro_prompt = f"""
    The game is about to begin. The setting is {setting}, {genre}. 
    Provide a dramatic and engaging introductory narrative (about 3-4 paragraphs). 
    This introduction should:
    1. Name the starting location (e.g., 'The Whispering Alley').
    2. Describe the scenery vividly.
    3. Present an immediate, intriguing event or challenge (the hook) that requires the players to act.
    4. End by asking the active player, {st.session_state['current_player']}, what they do next.
    """
    
    with st.spinner("Generating epic adventure hook..."):
        try:
            final_narrative_config = GenerateContentConfig(
                system_instruction=st.session_state["final_system_instruction"]
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=intro_prompt,
                config=final_narrative_config
            )
            
            st.session_state["history"] = []
            st.session_state["history"].append({"role": "assistant", "content": safe_model_text(response)})
            st.session_state["adventure_started"] = True # Mark the game as started
            st.session_state["page"] = "GAME" # Switch page to Game View
            st.rerun() # Rerun to show the new history

        except Exception as e:
            st.error(f"Failed to start adventure: {e}")

def save_game():
    """Saves the essential game state to Streamlit's file system as JSON."""
    if not st.session_state["adventure_started"]:
        st.warning("Adventure must be started to save game.")
        return

    game_state = {
        "history": st.session_state["history"],
        "characters": st.session_state["characters"],
        "system_instruction": st.session_state["final_system_instruction"],
        "current_player": st.session_state["current_player"],
        "adventure_started": st.session_state["adventure_started"],
        # Save widget values to restore the UI
        "setting": st.session_state["setup_setting"], 
        "genre": st.session_state["setup_genre"],
        "difficulty": st.session_state["setup_difficulty"],
        "custom_setting_description": st.session_state["custom_setting_description"],
    }
    
    st.session_state["saved_game_json"] = json.dumps(game_state, indent=2)
    st.success("Game state saved to memory. Use the Download button to secure your file!")

def load_game(uploaded_file):
    """Loads game state from an uploaded file."""
    if uploaded_file is not None:
        try:
            bytes_data = uploaded_file.read()
            loaded_data = json.loads(bytes_data)

            # Store data in staging variables to avoid the modification error
            st.session_state["__LOAD_DATA__"] = loaded_data
            st.session_state["__LOAD_FLAG__"] = True
            
            st.success("Adventure loaded successfully! Restarting session...")
            st.rerun() # Force a rerun to apply the staged data

        except Exception as e:
            st.error(f"Error loading file: {e}. Please ensure the file is valid JSON.")


# --- Check for Staged Load Data (Runs BEFORE Widgets are created) ---
if "__LOAD_FLAG__" in st.session_state and st.session_state["__LOAD_FLAG__"]:
    
    loaded_data = st.session_state["__LOAD_DATA__"]

    # Apply data directly to session state before any widgets are rendered
    st.session_state["history"] = loaded_data["history"]
    st.session_state["characters"] = loaded_data["characters"]
    st.session_state["final_system_instruction"] = loaded_data["system_instruction"]
    st.session_state["current_player"] = loaded_data["current_player"]
    st.session_state["adventure_started"] = loaded_data["adventure_started"]
    
    # Restore settings by setting the initial values for the selectboxes' keys
    st.session_state["setup_setting"] = loaded_data.get("setting", "Post-Apocalypse")
    st.session_state["setup_genre"] = loaded_data.get("genre", "Mutant Survival")
    st.session_state["setup_difficulty"] = loaded_data.get("difficulty", "Normal (Balanced)") 
    st.session_state["custom_setting_description"] = loaded_data.get("custom_setting_description", "")
    st.session_state["page"] = "GAME" # Force game page after load
    
    # Clear the staging variables
    st.session_state["__LOAD_FLAG__"] = False
    del st.session_state["__LOAD_DATA__"]


# --- Streamlit UI Setup ---

st.set_page_config(layout="wide")
st.title("🧙 RPG Storyteller DM (Powered by Gemini)")

# --- Initialize Session State (FINAL CHECK) ---
if "history" not in st.session_state: st.session_state["history"] = []
if "characters" not in st.session_state: st.session_state["characters"] = {}
if "current_player" not in st.session_state: st.session_state["current_player"] = None
if "final_system_instruction" not in st.session_state: st.session_state["final_system_instruction"] = None
if "new_player_name" not in st.session_state: st.session_state["new_player_name"] = "" 
if "adventure_started" not in st.session_state: st.session_state["adventure_started"] = False
if "saved_game_json" not in st.session_state: st.session_state["saved_game_json"] = ""
if "__LOAD_FLAG__" not in st.session_state: st.session_state["__LOAD_FLAG__"] = False
if "__LOAD_DATA__" not in st.session_state: st.session_state["__LOAD_DATA__"] = None
if "page" not in st.session_state: st.session_state["page"] = "SETUP" 
if "custom_setting_description" not in st.session_state: st.session_state["custom_setting_description"] = "" 
if "custom_character_description" not in st.session_state: st.session_state["custom_character_description"] = "" 
if "new_player_name_input_setup_value" not in st.session_state: st.session_state["new_player_name_input_setup_value"] = ""
if "setup_race" not in st.session_state: st.session_state["setup_race"] = "Human"


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
        
        # Difficulty selection
        st.subheader("Difficulty")
        _ = st.selectbox("Game Difficulty", list(DIFFICULTY_OPTIONS.keys()), key="setup_difficulty")
        st.caption(DIFFICULTY_OPTIONS[st.session_state["setup_difficulty"]])
        
        # Load Game moved here
        st.markdown("---")
        st.subheader("Load Existing Game")
        uploaded_file = st.file_uploader("Load Adventure File", type="json")
        if uploaded_file is not None and st.button("Load"):
            load_game(uploaded_file)


    with col_world_description:
        st.subheader("Custom World Details")
        st.markdown("Describe the location, climate, community disposition, or any key elements you want the DM to include in the campaign.")
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
        
        race_choices = RACE_OPTIONS.get(st.session_state["setup_setting"], ["Human"])
        _ = st.selectbox("Choose Race", race_choices, key="setup_race")
        
        selected_class_list = CLASS_OPTIONS[st.session_state.get('setup_setting', 'Classic Fantasy')]
        _ = st.selectbox("Choose Class/Role", selected_class_list, key="setup_class")
        
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
    
    # --- Define the two main columns (Center Chat + Right Stats) ---
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
    # RIGHT COLUMN (Active Player Stats - RENDERED IN MAIN BODY)
    # =========================================================================
    with col_stats:
        with st.container(border=True):
            st.header("Active Player Stats")
            
            active_char = st.session_state["characters"].get(st.session_state["current_player"])

            if st.session_state["characters"]:
                player_options = list(st.session_state["characters"].keys())
                default_index = player_options.index(st.session_state["current_player"]) if st.session_state["current_player"] in player_options else 0
                
                st.selectbox(
                    "Current Turn",
                    player_options,
                    key="player_selector",
                    index=default_index,
                    disabled=not game_started # Disable switching during core narrative responses
                )
                st.session_state["current_player"] = st.session_state["player_selector"]
                
                st.markdown("---")
                
                if active_char:
                    st.subheader(active_char['name'])
                    st.markdown(f"**Race:** {active_char.get('race', 'N/A')}")
                    st.markdown(f"**Class:** {active_char['race_class']}")
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("HP", active_char.get('current_hp', 0))
                    c2.metric("AC", compute_ac(active_char)[0], help=compute_ac(active_char)[1])
                    c3.metric("Sanity", active_char.get('morale_sanity', 100))

                    with st.expander("Abilities & Inventory", expanded=False):
                        # Ability Scores
                        st.markdown("**Ability Modifiers**")
                        c1,c2,c3 = st.columns(3); c4,c5,c6 = st.columns(3)
                        with c1: st.markdown(f"**STR**: {active_char.get('str_mod', 0)}")
                        with c2: st.markdown(f"**DEX**: {active_char.get('dex_mod', 0)}")
                        with c3: st.markdown(f"**CON**: {active_char.get('con_mod', 0)}")
                        with c4: st.markdown(f"**INT**: {active_char.get('int_mod', 0)}")
                        with c5: st.markdown(f"**WIS**: {active_char.get('wis_mod', 0)}")
                        with c6: st.markdown(f"**CHA**: {active_char.get('cha_mod', 0)}")
                        
                        st.markdown("---")
                        st.markdown("**Inventory**")
                        st.markdown(", ".join(active_char['inventory']))
                        
                    with st.expander("Equipment Slots & Spells", expanded=False):
                        # Equipment
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
                        # Spells (if applicable)
                        cls = canonical_class(active_char.get("race_class"))
                        class_spell_list = get_class_spell_list(cls, 1)
                        if class_spell_list:
                            slots = active_char["spell_slots"]["1"]
                            st.subheader("Spellcasting (Lv1)")
                            st.markdown(f"**Slots:** {slots['current']}/{slots['max']}")
                            st.markdown(f"**Prepared:** {', '.join(active_char['spells_prepared']) or '—'}")

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
            else:
                st.write("No characters created.")


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
            # 1. Add user message to display and history (with player name prepended)
            current_player_name = st.session_state["current_player"]
            active_char = st.session_state["characters"].get(current_player_name)
            
            full_prompt = f"({current_player_name}'s Turn): {prompt}"
            st.session_state["history"].append({"role": "user", "content": full_prompt})
            
            # --- Start Assistant Response ---
            
            with st.spinner("The DM is thinking..."):
                
                final_response_text = ""
                
                final_narrative_config = GenerateContentConfig(
                    system_instruction=st.session_state["final_system_instruction"]
                )
                
                # 2. Action Detection (The Gatekeeper)
                raw_roll = extract_roll(prompt)

                # =========================================================================
                # A) LOGIC CHECK (IF A ROLL IS DETECTED)
                # =========================================================================
                if raw_roll is not None:
                    st.toast(f"Skill Check Detected! Player {current_player_name} roll: {raw_roll}")
                    
                    logic_prompt = f"""
                    RESOLVE A PLAYER ACTION:
                    1. Character Stats (JSON): {json.dumps(active_char)}
                    2. Player Action: "{prompt}"
                    3. Task: Determine the appropriate attribute (e.g., Dexterity) and set a reasonable Difficulty Class (DC 10-20), adjusted by the current Difficulty Level. 
                    4. Calculate the result using the player's D20 roll ({raw_roll}) and the correct modifier from the character stats.
                    5. Return ONLY the JSON object following the SkillCheckResolution schema.
                    """
                    
                    try:
                        # 1st API Call: Logic Call (Forced JSON Output)
                        logic_response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=logic_prompt,
                            config=skill_check_config
                        )
                        
                        skill_check_outcome = json.loads(logic_response.text)
                        
                        # Prepare the display box content
                        roll = skill_check_outcome.get('player_d20_roll', 'N/A')
                        mod = skill_check_outcome.get('attribute_modifier', 'N/A')
                        total = skill_check_outcome.get('total_roll', 'N/A')
                        dc = skill_check_outcome.get('difficulty_class', 'N/A')
                        
                        # Prepare the HTML display box
                        combat_display = f"""
                        <div style='border: 2px solid green; padding: 10px; border-radius: 8px; background-color: #333333; color: white;'>
                        **{skill_check_outcome['outcome_result'].upper()}!** ({skill_check_outcome['attribute_used']} Check)
                        <hr style='border-top: 1px solid #555555; margin: 5px 0;'>
                        **Roll:** {roll} + **Mod:** {mod} = **{total}** (vs **DC:** {dc})
                        </div>
                        """
                        
                        # Display the mechanical result in the chat box
                        st.markdown(combat_display, unsafe_allow_html=True)
                        st.toast(f"Result: {skill_check_outcome['outcome_result']}")
                        
                        # Prepare the follow-up narrative prompt
                        follow_up_prompt = f"""
                        The player {current_player_name}'s risky action was RESOLVED. The EXACT JSON outcome was: {json.dumps(skill_check_outcome)}.
                        1. Narrate the vivid, descriptive consequence of this result.
                        2. Update the scene based on the outcome and ask the player what they do next.
                        """
                        
                        # Add the JSON resolution and follow-up prompt to history for the final narrative call
                        st.session_state["history"].append({"role": "assistant", "content": f"//Mechanics: {json.dumps(skill_check_outcome)}//"})
                        st.session_state["history"].append({"role": "user", "content": follow_up_prompt})


                    except Exception as e:
                        st.error(f"Logic Call Failed: {e}")
                        st.session_state["history"].pop() # Remove the user prompt that caused the failure


                # =========================================================================
                # B) NARRATIVE CALL (ALWAYS RUNS, or FOLLOWS UP THE LOGIC CALL)
                # =========================================================================
                
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
                
                # Force a final rerun to display the response and clear the input box
                st.rerun()
