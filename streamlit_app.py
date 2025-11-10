import streamlit as st
st.set_page_config(layout="wide")

import json
import re
from google import genai
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

# ---- Style: widen sidebar (~10% more than before) ----
_SIDEBAR_CSS = """
<style>
/* Wider sidebar for the character sheet */
[data-testid="stSidebar"] { width: 480px; min-width: 480px; }
@media (max-width: 1200px) {
  [data-testid="stSidebar"] { width: 410px; min-width: 410px; }
}
/* Tighten expander body spacing a bit */
section[aria-label="Active Player"] div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.25rem; }
</style>
"""
st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)

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

SYSTEM_INSTRUCTION_TEMPLATE = """
You are the ultimate Dungeon Master (DM) and Storyteller, running a persistent TTRPG for {player_count} players in the **{setting}, {genre}** setting.
IMPORTANT: Integrate the following user-provided details into the world and character backgrounds:
Setting Details: {custom_setting_description}
---
Game Rules:
1. **Free Actions:** Simple actions like looking around, dropping an item, or shouting a brief warning are **Free Actions** and do not end the player's turn or require a check. Only complex, risky, or time-consuming actions require a skill check.
2. **Combat/Skill Check Display:** After resolving a skill check, narrate the outcome vividly. Include a mechanical summary showing the DC vs. the result, e.g.: "You swing your sword. (Monster AC 12 vs Roll 12 + Mod 4 = 16. Success)".
---
Your tone must match the genre: be immersive, tense, and dramatic.
Your output must be pure, flowing narrative text. DO NOT include JSON unless specifically asked to perform a check.
"""

# --- Schemas ---

class CharacterSheet(BaseModel):
    name: str = Field(description="The player's chosen name.")
    race_class: str = Field(description="The character's core identity.")
    str_mod: int = Field(description="Strength Modifier.")
    dex_mod: int = Field(description="Dexterity Modifier.")
    con_mod: int = Field(description="Constitution Modifier.")
    int_mod: int = Field(description="Intelligence Modifier.")
    wis_mod: int = Field(description="Wisdom Modifier.")
    cha_mod: int = Field(description="Charisma Modifier.")
    current_hp: int = Field(description="The character's current health.")
    morale_sanity: int = Field(description="The character's mental fortitude, starting at 100.")
    inventory: List[str] = Field(description="A list of 3-5 starting major gear items.")
    experience: int = Field(description="Starting experience points (always 0).")

character_creation_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)

class SkillCheckResolution(BaseModel):
    action: str = Field(description="The action the player attempted.")
    attribute_used: str = Field(description="The core attribute used for the check (e.g., 'Dexterity').")
    difficulty_class: int = Field(description="The DC set by the DM/Gemini.")
    player_d20_roll: int = Field(description="The raw D20 roll provided.")
    attribute_modifier: int = Field(description="The modifier used in the calculation.")
    total_roll: int = Field(description="The calculated result.")
    outcome_result: str = Field(description="Result: 'Success', 'Failure', 'Critical Success', or 'Critical Failure'.")
    hp_change: int = Field(description="Damage taken or health gained. Default 0.", default=0)
    consequence_narrative: str = Field(description="Brief description of the immediate mechanical consequence.")

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
    "blade","hammer","sabre","saber","rapier","longsword","shortsword","katana",
    "pistol","rifle","shotgun","smg","revolver","gun"
]
_SHIELD_WORDS = ["shield","buckler","kite shield","tower shield"]
_ARMOR_WORDS = [
    "armor","armour","leather","chain","chainmail","mail","scale","plate",
    "breastplate","brigandine","vest","kevlar","coat","jacket","robes","robe","shirt","clothes","tunic"
]
_BOOTS_WORDS = ["boots","shoes","greaves","sandals","sabatons"]
_RING_WORDS = ["ring","band","signet"]
_NECK_WORDS = ["necklace","amulet","pendant","torc"]
_HEAD_WORDS = ["helmet","helm","diadem","crown","hat","hood","cap"]

def is_match(word_list, name: str) -> bool:
    low = name.lower()
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
    if not slots:
        # Fallback: let the user choose any slot
        slots = SLOTS.copy()
    # Deduplicate while preserving order
    seen = set(); ordered = []
    for s in slots:
        if s not in seen:
            seen.add(s); ordered.append(s)
    return ordered

def parse_bonuses(item_name: str) -> str:
    """Find things like '+1', '+2 to attack', etc."""
    bonuses = []
    for m in re.findall(r"\+\s*\d+(?:\s*(?:to|vs\.?)\s*[A-Za-z ]+)?", item_name):
        bonuses.append(m.strip())
    return ", ".join(bonuses)

def ensure_equipped_slots(char: dict):
    """
    Ensure 'equipped' exists as a slot dict:
    { slot: {"item": str, "bonuses": str} or None }
    """
    if "equipped" not in char or not isinstance(char["equipped"], dict):
        char["equipped"] = {}
    for s in SLOTS:
        char["equipped"].setdefault(s, None)

def unequip_slot(char: dict, slot: str):
    ensure_equipped_slots(char)
    char["equipped"][slot] = None

def equip_to_slot(char: dict, slot: str, item_name: str, bonuses: Optional[str] = None):
    ensure_equipped_slots(char)
    if bonuses is None:
        bonuses = parse_bonuses(item_name)
    # Remove the same item from any other slot (avoid duplicates)
    for s in SLOTS:
        if char["equipped"].get(s) and char["equipped"][s]["item"] == item_name:
            char["equipped"][s] = None
    # Put it in the chosen slot
    char["equipped"][slot] = {"item": item_name, "bonuses": bonuses}

def auto_equip_defaults(char: dict):
    """
    Fill empty slots with sensible defaults from inventory.
    - weapon -> right_arm
    - shield -> left_arm
    - armor -> body
    - boots -> feet
    - rings -> right_hand then left_hand
    - necklace -> neck
    - headwear -> head
    """
    ensure_equipped_slots(char)
    inv = char.get("inventory", []) or []

    def first_match(words): 
        for i in inv:
            if is_match(words, i):
                return i
        return None

    if not char["equipped"]["right_arm"]:
        w = first_match(_WEAPON_WORDS)
        if w: equip_to_slot(char, "right_arm", w)
    if not char["equipped"]["left_arm"]:
        sh = first_match(_SHIELD_WORDS)
        if sh: equip_to_slot(char, "left_arm", sh)

    if not char["equipped"]["body"]:
        a = first_match(_ARMOR_WORDS)
        if a: equip_to_slot(char, "body", a)

    if not char["equipped"]["feet"]:
        b = first_match(_BOOTS_WORDS)
        if b: equip_to_slot(char, "feet", b)

    # Rings: try to fill right then left
    if not char["equipped"]["right_hand"]:
        r = first_match(_RING_WORDS)
        if r: equip_to_slot(char, "right_hand", r)
    if not char["equipped"]["left_hand"]:
        # If right used the same ring name, find a different ring (best effort)
        r2 = None
        for i in inv:
            if is_match(_RING_WORDS, i) and (not char["equipped"]["right_hand"] or char["equipped"]["right_hand"]["item"] != i):
                r2 = i; break
        if r2: equip_to_slot(char, "left_hand", r2)

    if not char["equipped"]["neck"]:
        n = first_match(_NECK_WORDS)
        if n: equip_to_slot(char, "neck", n)

    if not char["equipped"]["head"]:
        h = first_match(_HEAD_WORDS)
        if h: equip_to_slot(char, "head", h)

# --- Model helpers ---

def get_api_contents(history_list):
    contents = []
    for msg in history_list:
        if msg.get("content") and isinstance(msg["content"], str):
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def safe_model_text(resp) -> str:
    try:
        if hasattr(resp, "text") and resp.text and resp.text.strip():
            return resp.text.strip()
        if hasattr(resp, "candidates") and resp.candidates:
            for c in resp.candidates:
                if hasattr(c, "content") and getattr(c.content, "parts", None):
                    for p in c.content.parts:
                        if getattr(p, "text", None) and p.text.strip():
                            return p.text.strip()
        if hasattr(resp, "prompt_feedback") and getattr(resp.prompt_feedback, "block_reason", None):
            return f"(Model returned no text; block_reason={resp.prompt_feedback.block_reason})"
    except Exception:
        pass
    return "(No model text returned. Try a shorter action, or include a 'roll 12' style number for a quick skill check.)"

# --- Character creation / game flow ---

def create_new_character_handler(setting, genre, player_name, selected_class, custom_char_desc, difficulty):
    if not player_name or player_name in st.session_state["characters"]:
        st.error("Please enter a unique name for the new character.")
        return

    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=len(st.session_state["characters"]) + 1,
        custom_setting_description=st.session_state['custom_setting_description'],
        difficulty_level=difficulty,
        difficulty_rules=DIFFICULTY_OPTIONS[difficulty]
    )
    
    creation_prompt = f"""
    Based on the setting: {setting}, genre: {genre}. Create a starting character named {player_name}.
    The character's primary role must be: {selected_class}.
    Player's Custom Description: {custom_char_desc if custom_char_desc else "No specific background details provided. Create a generic background appropriate for the class."}
    The character should be balanced, attribute modifiers should range from -1 to +3, starting HP should be 20, and Morale/Sanity must start at 100.
    Fill in ALL fields in the required JSON schema.
    """
    
    with st.spinner(f"Creating survivor {player_name} for {genre}..."):
        try:
            char_config = GenerateContentConfig(
                system_instruction=final_system_instruction,
                response_mime_type="application/json",
                response_schema=CharacterSheet,
            )
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=creation_prompt,
                config=char_config
            )
            raw = resp.text or ""
            if not raw.strip():
                fail_note = f"Character API returned no text. {safe_model_text(resp)}"
                st.session_state["history"].append({"role": "assistant", "content": fail_note})
                st.error("Character creation returned no text. Try again.")
                return

            char_data = json.loads(raw)
            char_data['name'] = player_name

            # Ensure fields & equip slots
            for k in ["str_mod","dex_mod","con_mod","int_mod","wis_mod","cha_mod"]:
                char_data.setdefault(k, 0)
            ensure_equipped_slots(char_data)
            auto_equip_defaults(char_data)

            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            if not st.session_state["current_player"]:
                st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"Player {player_name} added to the party. Ready for adventure initiation."})

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}")
            st.session_state["history"].append({"role": "assistant", "content": f"Character creation error: {e}"})

    st.session_state["new_player_name_input_setup_value"] = ""
    st.session_state["custom_character_description"] = ""
    st.rerun() 

def extract_roll(text):
    match = re.search(r'\b(roll|rolls|rolled|try|trying|tries)\s+(\d{1,2})\b', text, re.IGNORECASE)
    if match:
        val = int(match.group(2))
        if 1 <= val <= 20:
            return val
    return None

def start_adventure_handler():
    start_adventure(st.session_state["setup_setting"], st.session_state["setup_genre"])

def start_adventure(setting, genre):
    if st.session_state["current_player"] is None:
        st.error("Please create at least one character before starting the adventure!")
        return
        
    # Auto-equip defaults for all characters at the start if any slot is empty
    for _name, _char in st.session_state["characters"].items():
        ensure_equipped_slots(_char)
        auto_equip_defaults(_char)
    
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
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=intro_prompt,
                config=final_narrative_config
            )
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
    st.success("Game state saved to memory. Use the Download button to secure your file!")

def load_game(uploaded_file):
    if uploaded_file is not None:
        try:
            bytes_data = uploaded_file.read()
            loaded_data = json.loads(bytes_data)
            st.session_state["__LOAD_DATA__"] = loaded_data
            st.session_state["__LOAD_FLAG__"] = True
            st.success("Adventure loaded successfully! Restarting session...")
            st.rerun()
        except Exception as e:
            st.error(f"Error loading file: {e}. Please ensure the file is valid JSON.")

# --- staged load (before widgets) ---
if "__LOAD_FLAG__" in st.session_state and st.session_state["__LOAD_FLAG__"]:
    loaded_data = st.session_state["__LOAD_DATA__"]
    st.session_state["history"] = loaded_data["history"]
    st.session_state["characters"] = loaded_data["characters"]
    st.session_state["final_system_instruction"] = loaded_data["system_instruction"]
    st.session_state["current_player"] = loaded_data["current_player"]
    st.session_state["adventure_started"] = loaded_data["adventure_started"]
    st.session_state["setup_setting"] = loaded_data.get("setting", "Post-Apocalypse")
    st.session_state["setup_genre"] = loaded_data.get("genre", "Mutant Survival")
    st.session_state["setup_difficulty"] = loaded_data.get("difficulty", "Normal (Balanced)") 
    st.session_state["custom_setting_description"] = loaded_data.get("custom_setting_description", "")
    # Ensure equipped slots for all characters after load
    for k, v in st.session_state["characters"].items():
        ensure_equipped_slots(v)
    st.session_state["page"] = "GAME"
    st.session_state["__LOAD_FLAG__"] = False
    del st.session_state["__LOAD_DATA__"]

# --- Init session state ---
st.title("🧙 RPG Storyteller DM (Powered by Gemini)")

for key, default in [
    ("history", []),
    ("characters", {}),
    ("current_player", None),
    ("final_system_instruction", None),
    ("new_player_name", ""),
    ("adventure_started", False),
    ("saved_game_json", ""),
    ("__LOAD_FLAG__", False),
    ("__LOAD_DATA__", None),
    ("page", "SETUP"),
    ("custom_setting_description", ""),
    ("custom_character_description", ""),
    ("new_player_name_input_setup_value", "")
]:
    if key not in st.session_state:
        st.session_state[key] = default

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
        st.markdown("Describe key elements you want in the campaign.")
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
            placeholder="Example: A tall, paranoid ex-corporate security guard with a visible cybernetic eye and a strong fear of heights."
        )

    if col_char_creation.button("Add Character to Party"):
        if st.session_state["new_player_name_input_setup"]:
            create_new_character_handler(
                st.session_state["setup_setting"], 
                st.session_state["setup_genre"], 
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
    col_chat = st.container()
    game_started = st.session_state["adventure_started"]

    # ---------------------- SIDEBAR ----------------------
    with st.sidebar:
        # Active Player at top
        with st.expander("Active Player", expanded=True):
            if st.session_state["characters"]:
                player_options = list(st.session_state["characters"].keys())
                default_index = (
                    player_options.index(st.session_state["current_player"])
                    if st.session_state["current_player"] in player_options else 0
                )

                def _on_player_change():
                    st.session_state["current_player"] = st.session_state["player_selector"]
                    st.rerun()

                st.selectbox(
                    "Current Turn",
                    player_options,
                    key="player_selector",
                    index=default_index,
                    disabled=not game_started,
                    on_change=_on_player_change
                )

                active_char = st.session_state["characters"].get(st.session_state["current_player"])
                st.markdown("---")
                if active_char:
                    ensure_equipped_slots(active_char)
                    st.markdown(f"**Name:** {active_char.get('name','')}")
                    st.markdown(f"**Class:** {active_char.get('race_class','')}")
                    st.markdown(f"**HP:** {active_char.get('current_hp','')}")
                    st.markdown(f"**Sanity/Morale:** {active_char.get('morale_sanity','')}")

                    # Inventory with slot selector + equip buttons
                    st.markdown("**Inventory:**")
                    if active_char.get("inventory"):
                        for idx, item in enumerate(active_char["inventory"]):
                            # Detect candidate slots
                            candidates = detect_candidate_slots(item)
                            cols = st.columns([4,3,2])
                            with cols[0]:
                                st.markdown(f"- {item}")
                            with cols[1]:
                                slot_choice = st.selectbox(
                                    "Slot",
                                    [SLOT_LABEL[s] for s in candidates],
                                    key=f"slot_select_{active_char['name']}_{idx}"
                                )
                            with cols[2]:
                                slot_key = {v:k for k,v in SLOT_LABEL.items()}[slot_choice]
                                # Is this item already in some slot?
                                item_occupied_slot = None
                                for s in SLOTS:
                                    if active_char["equipped"].get(s) and active_char["equipped"][s]["item"] == item:
                                        item_occupied_slot = s
                                        break
                                if item_occupied_slot:
                                    if st.button("Unequip", key=f"unequip_btn_{active_char['name']}_{idx}"):
                                        unequip_slot(active_char, item_occupied_slot)
                                        st.rerun()
                                else:
                                    if st.button("Equip", key=f"equip_btn_{active_char['name']}_{idx}"):
                                        equip_to_slot(active_char, slot_key, item)
                                        st.rerun()
                    else:
                        st.caption("— (empty)")

                    # Equipped by slots
                    st.markdown("**Equipped (by slot):**")
                    for s in SLOTS:
                        eq = active_char["equipped"].get(s)
                        label = SLOT_LABEL[s]
                        cols = st.columns([6,3,2])
                        with cols[0]:
                            if eq:
                                bonuses = f" _(bonuses: {eq.get('bonuses','')})_" if eq.get("bonuses") else ""
                                st.markdown(f"- **{label}:** {eq['item']}{bonuses}")
                            else:
                                st.markdown(f"- **{label}:** —")
                        with cols[1]:
                            if eq:
                                st.caption("equipped")
                            else:
                                st.caption("")
                        with cols[2]:
                            if eq and st.button("Unequip", key=f"slot_unequip_{active_char['name']}_{s}"):
                                unequip_slot(active_char, s)
                                st.rerun()

                    st.markdown("---")
                    st.markdown("**Ability Modifiers**")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**STR**: {active_char.get('str_mod', 0)}")
                    with c2:
                        st.markdown(f"**DEX**: {active_char.get('dex_mod', 0)}")
                    with c3:
                        st.markdown(f"**CON**: {active_char.get('con_mod', 0)}")
                    c4, c5, c6 = st.columns(3)
                    with c4:
                        st.markdown(f"**INT**: {active_char.get('int_mod', 0)}")
                    with c5:
                        st.markdown(f"**WIS**: {active_char.get('wis_mod', 0)}")
                    with c6:
                        st.markdown(f"**CHA**: {active_char.get('cha_mod', 0)}")
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
            st.download_button(
                label="Download Game File",
                data=st.session_state["saved_game_json"],
                file_name="gemini_rpg_save.json",
                mime="application/json",
            )

    # ---------------------- MAIN CHAT AREA ----------------------
    with col_chat:
        st.header("The Story Log")
        for message in reversed(st.session_state["history"]):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # ---------------------- INPUT AREA ----------------------
    if game_started:
        prompt = st.chat_input("What do you do?")
        if prompt:
            current_player_name = st.session_state["current_player"]
            active_char = st.session_state["characters"].get(current_player_name)
            # Ensure equipped structure always exists
            ensure_equipped_slots(active_char)

            full_prompt = f"({current_player_name}'s Turn): {prompt}"
            st.session_state["history"].append({"role": "user", "content": full_prompt})
            
            with st.spinner("The DM is thinking..."):
                final_narrative_config = GenerateContentConfig(
                    system_instruction=st.session_state["final_system_instruction"]
                )
                raw_roll = extract_roll(prompt)

                # --- Logic call if a roll is detected ---
                if raw_roll is not None:
                    st.toast(f"Skill Check Detected! Player {current_player_name} roll: {raw_roll}")

                    # Condensed equipped summary for the model
                    equipped_summary = {
                        SLOT_LABEL[s]: active_char["equipped"][s] for s in SLOTS if active_char["equipped"].get(s)
                    }

                    logic_prompt = f"""
                    RESOLVE A PLAYER ACTION:
                    1. Character Stats (JSON): {json.dumps(active_char)}
                    2. Equipped (by slot): {json.dumps(equipped_summary)}
                    3. Player Action: "{prompt}"
                    4. Task: Determine the appropriate attribute (e.g., Dexterity) and set a reasonable Difficulty Class (DC 10-20), adjusted by the current Difficulty Level. 
                    5. Calculate the result using the player's D20 roll ({raw_roll}), the correct modifier from the character stats, and consider equipped items' bonuses if applicable.
                    6. Return ONLY the JSON object following the SkillCheckResolution schema.
                    """
                    try:
                        logic_config = GenerateContentConfig(
                            system_instruction=st.session_state["final_system_instruction"],
                            response_mime_type="application/json",
                            response_schema=SkillCheckResolution,
                        )
                        logic_resp = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=logic_prompt,
                            config=logic_config
                        )
                        raw_logic = logic_resp.text or ""
                        if not raw_logic.strip():
                            st.session_state["history"].append({"role": "assistant", "content": f"(No logic text) {safe_model_text(logic_resp)}"})
                        else:
                            skill = json.loads(raw_logic)
                            roll = skill.get('player_d20_roll', 'N/A')
                            mod = skill.get('attribute_modifier', 'N/A')
                            total = skill.get('total_roll', 'N/A')
                            dc = skill.get('difficulty_class', 'N/A')
                            combat_display = f"""
                            <div style="border:2px solid #2e7d32;padding:10px;border-radius:8px;background-color:#1e1e1e;color:#ffffff;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
                              <div style="font-weight:700;margin-bottom:6px;">{skill.get('outcome_result','').upper()}! ({skill.get('attribute_used','')} Check)</div>
                              <hr style="border:none;border-top:1px solid #555;margin:6px 0;">
                              <div><strong>Roll:</strong> {roll} + <strong>Mod:</strong> {mod} = <strong>{total}</strong> (vs <strong>DC:</strong> {dc})</div>
                            </div>
                            """
                            st.markdown(combat_display, unsafe_allow_html=True)
                            st.toast(f"Result: {skill.get('outcome_result','')}")
                            follow_up = f"""
                            The player {current_player_name}'s risky action was RESOLVED. The EXACT JSON outcome was: {json.dumps(skill)}.
                            1. Narrate the vivid, descriptive consequence of this result.
                            2. Update the scene based on the outcome and ask the player what they do next.
                            """
                            st.session_state["history"].append({"role": "assistant", "content": f"//Mechanics: {json.dumps(skill)}//"})
                            st.session_state["history"].append({"role": "user", "content": follow_up})
                    except Exception as e:
                        st.session_state["history"].append({"role": "assistant", "content": f"Logic error: {e}"})

                # --- Narrative call (always) ---
                try:
                    narr_resp = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=get_api_contents(st.session_state["history"]),
                        config=final_narrative_config
                    )
                    text = safe_model_text(narr_resp)
                    st.session_state["history"].append({"role": "assistant", "content": text})
                except Exception as e:
                    st.session_state["history"].append({"role": "assistant", "content": f"Narrative error: {e}"})
                
                st.rerun()
