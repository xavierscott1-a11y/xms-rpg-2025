import streamlit as st
st.set_page_config(layout="wide")

import json
import re
from google import genai
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List

# ---- Style: widen sidebar (~25%) and adjust main area ----
_SIDEBAR_CSS = """
<style>
/* Make the sidebar wider and shift main content accordingly */
[data-testid="stSidebar"] { width: 420px; min-width: 420px; }
@media (max-width: 1200px) {
  [data-testid="stSidebar"] { width: 360px; min-width: 360px; }
}
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

# --- Helpers: equipment, parsing, API text ---

_WEAPON_WORDS = [
    "sword","dagger","axe","mace","spear","bow","crossbow","staff","club",
    "blade","hammer","sabre","saber","rapier","longsword","shortsword","katana",
    "pistol","rifle","shotgun","smg","smg.","revolver"
]
_ARMOR_WORDS = [
    "armor","armour","leather","chain","chainmail","mail","scale","plate",
    "breastplate","brigandine","shield","helmet","helm","vest","kevlar"
]

def is_weapon(item_name: str) -> bool:
    name = item_name.lower()
    return any(w in name for w in _WEAPON_WORDS)

def is_armor(item_name: str) -> bool:
    name = item_name.lower()
    return any(w in name for w in _ARMOR_WORDS)

def parse_bonuses(item_name: str) -> str:
    """
    Quick-n-dirty bonus parser: finds things like '+1', '+2 to attack', etc.
    If none found, empty string.
    """
    name = item_name
    # Collect any +N or +N to <stat> patterns
    bonuses = []
    for m in re.findall(r"\+\s*\d+(?:\s*(?:to|vs\.?)\s*[A-Za-z ]+)?", name):
        bonuses.append(m.strip())
    return ", ".join(bonuses)

def ensure_equipped_field(char: dict):
    if "equipped" not in char or not isinstance(char["equipped"], list):
        char["equipped"] = []

def is_item_equipped(char: dict, item_name: str) -> bool:
    ensure_equipped_field(char)
    return any(eq.get("item") == item_name for eq in char["equipped"])

def equip_item(char: dict, item_name: str, bonuses: str = ""):
    ensure_equipped_field(char)
    if not is_item_equipped(char, item_name):
        if not bonuses:
            bonuses = parse_bonuses(item_name)
        char["equipped"].append({"item": item_name, "bonuses": bonuses})

def unequip_item(char: dict, item_name: str):
    ensure_equipped_field(char)
    char["equipped"] = [eq for eq in char["equipped"] if eq.get("item") != item_name]

def auto_equip_defaults(char: dict):
    """
    If nothing is equipped, auto-equip first weapon and first armor found in inventory.
    """
    ensure_equipped_field(char)
    if char["equipped"]:
        return
    inv = char.get("inventory", []) or []
    first_weapon = next((i for i in inv if is_weapon(i)), None)
    first_armor  = next((i for i in inv if is_armor(i)), None)
    if first_weapon:
        equip_item(char, first_weapon)
    if first_armor:
        equip_item(char, first_armor)

def get_api_contents(history_list):
    """Convert Streamlit history to Google GenAI Content list."""
    contents = []
    for msg in history_list:
        if msg.get("content") and isinstance(msg["content"], str):
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def safe_model_text(resp) -> str:
    """Be resilient to empty .text; try common places before giving a readable fallback."""
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

            # Ensure optional fields exist for display & auto-equip basics
            char_data.setdefault("equipped", [])
            for mod_key in ["str_mod","dex_mod","con_mod","int_mod","wis_mod","cha_mod"]:
                char_data.setdefault(mod_key, 0)
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
        
    # Auto-equip defaults for all characters at the start of the game if not already equipped
    for _name, _char in st.session_state["characters"].items():
        ensure_equipped_field(_char)
        if not _char["equipped"]:
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
    # Ensure equipped exists for all characters after load
    for k, v in st.session_state["characters"].items():
        v.setdefault("equipped", [])
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
                    # Ensure equipped exists & attempt default equip if somehow empty
                    ensure_equipped_field(active_char)
                    if not active_char["equipped"]:
                        auto_equip_defaults(active_char)

                    st.markdown(f"**Name:** {active_char.get('name','')}")
                    st.markdown(f"**Class:** {active_char.get('race_class','')}")
                    st.markdown(f"**HP:** {active_char.get('current_hp','')}")
                    st.markdown(f"**Sanity/Morale:** {active_char.get('morale_sanity','')}")
                    
                    # Inventory + Equip/Unequip controls
                    st.markdown("**Inventory:**")
                    if active_char.get("inventory"):
                        for idx, item in enumerate(active_char["inventory"]):
                            equipped_flag = is_item_equipped(active_char, item)
                            cols = st.columns([4,2,3])
                            with cols[0]:
                                st.markdown(f"- {item}")
                            with cols[1]:
                                if equipped_flag:
                                    if st.button("Unequip", key=f"unequip_{active_char['name']}_{idx}"):
                                        unequip_item(active_char, item)
                                        st.rerun()
                                else:
                                    if st.button("Equip", key=f"equip_{active_char['name']}_{idx}"):
                                        equip_item(active_char, item)  # auto-parse bonuses
                                        st.rerun()
                            with cols[2]:
                                # Show/preview parsed bonuses (read-only hint)
                                hint = parse_bonuses(item)
                                if hint:
                                    st.caption(f"bonuses: {hint}")
                    else:
                        st.caption("— (empty)")

                    # Equipped Items + Bonuses
                    st.markdown("**Equipped:**")
                    if active_char["equipped"]:
                        for eq_idx, eq in enumerate(active_char["equipped"]):
                            item = eq.get("item", "Unknown item")
                            bonuses = eq.get("bonuses", "")
                            st.markdown(f"- {item}" + (f" _(bonuses: {bonuses})_" if bonuses else ""))
                    else:
                        st.caption("None equipped")

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
                    logic_prompt = f"""
                    RESOLVE A PLAYER ACTION:
                    1. Character Stats (JSON): {json.dumps(active_char)}
                    2. Equipped Items with Bonuses: {json.dumps(active_char.get('equipped', []))}
                    3. Player Action: "{prompt}"
                    4. Task: Determine the appropriate attribute (e.g., Dexterity) and set a reasonable Difficulty Class (DC 10-20), adjusted by the current Difficulty Level. 
                    5. Calculate the result using the player's D20 roll ({raw_roll}), the correct modifier from the character stats, and consider equipped bonuses if applicable.
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
