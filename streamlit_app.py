import streamlit as st
import os
import json
import re
from google import genai
# Necessary imports for structured data and content types
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List, Optional

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

# Defined settings and genres for selection
SETTINGS_OPTIONS = {
    "Classic Fantasy": ["High Magic Quest", "Gritty Dungeon Crawl", "Political Intrigue"],
    "Post-Apocalypse": ["Mutant Survival", "Cybernetic Wasteland", "Resource Scarcity"],
    "Cyberpunk": ["Corporate Espionage", "Street Gang Warfare", "AI Revolution"],
    "Modern Fantasy": ["Urban Occult Detective", "Hidden Magic Conspiracy", "Campus Supernatural Drama"],
    "Horror": ["Cosmic Dread (Lovecraftian)", "Slasher Survival", "Gothic Vampire Intrigue"],
    "Spycraft": ["Cold War Espionage", "High-Tech Corporate Infiltration", "Shadowy Global Syndicate"],
}

# System Instruction Template - Set the core DM rules
SYSTEM_INSTRUCTION_TEMPLATE = """
You are the ultimate Dungeon Master (DM) and Storyteller, running a persistent TTRPG for {player_count} players in the **{setting}, {genre}** setting.
Your tone must match the genre: be immersive, tense, and dramatic.
When a skill check outcome (JSON) is provided to you, you must vividly integrate that exact result into the next narrative scene.
Your output must be pure, flowing narrative text. DO NOT include JSON unless specifically asked to perform a check.
"""

# --- Schemas (Required for Structured Output) ---

# Define Character Sheet Schema
class CharacterSheet(BaseModel):
    """The full character data structure."""
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

# Define Character Creation Configuration
character_creation_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)

# Define Skill Check Schema
class SkillCheckResolution(BaseModel):
    """Structured data for resolving a single player action."""
    action: str = Field(description="The action the player attempted.")
    attribute_used: str = Field(description="The core attribute used for the check (e.g., 'Dexterity').")
    difficulty_class: int = Field(description="The DC set by the DM/Gemini.")
    player_d20_roll: int = Field(description="The raw D20 roll the player provided.")
    attribute_modifier: int = Field(description="The modifier used in the calculation.")
    total_roll: int = Field(description="The calculated result.")
    outcome_result: str = Field(description="The result.")
    hp_change: int = Field(description="Damage taken or health gained. Default 0.", default=0)
    consequence_narrative: str = Field(description="A brief description of the immediate mechanical consequence.")

# Define Skill Check Configuration
skill_check_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=SkillCheckResolution,
)


# --- Helper Functions ---

def get_api_contents(history_list):
    """Converts Streamlit history format to API content format."""
    contents = []
    for msg in history_list:
        if msg["content"] and isinstance(msg["content"], str):
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def create_new_character(setting, genre, player_name):
    """Function to call the API and create a character JSON."""
    
    # Check if name is provided and unique
    if not player_name or player_name in st.session_state["characters"]:
        st.error("Please enter a unique name for the new character.")
        return

    # 1. Update the System Instruction with the user's choices
    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=len(st.session_state["characters"]) + 1 # Dynamic player count
    )
    
    creation_prompt = f"""
    Based on the setting: {setting} and the genre: {genre}, create a starting character named {player_name}.
    The character should be balanced, attribute modifiers should range from -1 to +3, starting HP should be 20, and Morale/Sanity must start at 100.
    Fill in ALL fields in the required JSON schema.
    """

    with st.spinner(f"Creating survivor {player_name} for {genre}..."):
        try:
            # We pass the dynamically created system instruction for the character creation call
            temp_config = GenerateContentConfig(
                system_instruction=final_system_instruction
            )
            
            char_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=creation_prompt,
                config=character_creation_config
            )
            char_data = json.loads(char_response.text)
            char_data['name'] = player_name # Ensure the name is exactly what the user input

            # Store the character and set the active player
            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"Player {player_name} is ready! Welcome. You are the active player."})

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}. Try a simpler name.")

def extract_roll(text):
    """Helper function to extract a number (1-20) indicating a dice roll."""
    # Searches for a number between 1 and 20 near keywords like 'roll' or 'try'
    match = re.search(r'\b(roll|rolls|rolled|try|trying|tries)\s+(\d{1,2})\b', text, re.IGNORECASE)
    if match and 1 <= int(match.group(2)) <= 20:
        return int(match.group(2))
    return None


# --- Streamlit UI Setup ---

st.set_page_config(layout="wide")
st.title("🧙 RPG Storyteller DM (Powered by Gemini)")

# --- Initialize Session State ---
if "history" not in st.session_state:
    st.session_state["history"] = []
if "characters" not in st.session_state:
    st.session_state["characters"] = {}
if "current_player" not in st.session_state:
    st.session_state["current_player"] = None
if "final_system_instruction" not in st.session_state:
    st.session_state["final_system_instruction"] = None


# --- Sidebar (Settings, Character Sheet & Controls) ---
st.sidebar.header("Game Settings")

game_started = bool(st.session_state["current_player"])
selected_setting = st.sidebar.selectbox("Choose Setting", list(SETTINGS_OPTIONS.keys()), disabled=game_started)
selected_genre = st.sidebar.selectbox("Choose Genre", SETTINGS_OPTIONS[selected_setting], disabled=game_started)


st.sidebar.header("Roster & Controls")

# Input field for new character name
new_player_name = st.sidebar.text_input("New Player Name", key="new_player_name", disabled=game_started and st.session_state["new_player_name"] == "")

# Character Creation Button: Requires a name and calls the updated function
if st.sidebar.button("Add Character to Game", disabled=game_started and not new_player_name):
    # Pass the name from the input field
    create_new_character(selected_setting, selected_genre, new_player_name)

# Player Rotation Dropdown/Selector
if st.session_state["characters"]:
    player_options = list(st.session_state["characters"].keys())
    
    # Ensure current_player is in options, set initial index
    if st.session_state["current_player"] in player_options:
        default_index = player_options.index(st.session_state["current_player"])
    else:
        default_index = 0
    
    st.sidebar.selectbox(
        "Active Player Turn",
        player_options,
        key="player_selector",
        index=default_index
    )
    # Update current_player state based on selector
    st.session_state["current_player"] = st.session_state["player_selector"]


# Display Active Player Sheet (Uses the selected player)
st.sidebar.header("Current Player Stats")
active_char = st.session_state["characters"].get(st.session_state["current_player"])

if active_char:
    st.sidebar.markdown(f"**Name:** {active_char['name']}")
    st.sidebar.markdown(f"**Class:** {active_char['race_class']}")
    st.sidebar.markdown(f"**HP:** {active_char['current_hp']}")
    st.sidebar.markdown(f"**Sanity:** {active_char['morale_sanity']}")
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Inventory:** " + ", ".join(active_char['inventory']))
else:
    st.sidebar.write("No characters created.")


# --- Main Game Loop Display ---
for message in st.session_state["history"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --- User Input and API Call Logic ---
prompt = st.chat_input("What do you do?")

if prompt:
    # 1. Basic Checks
    if not st.session_state["current_player"]:
        st.warning("Please create a character first!")
        st.stop()
    
    current_player_name = st.session_state["current_player"]
    active_char = st.session_state["characters"].get(current_player_name)
    
    # 2. Add user message to display and history (with player name prepended)
    full_prompt = f"({current_player_name}'s Turn): {prompt}"
    st.session_state["history"].append({"role": "user", "content": full_prompt})
    with st.chat_message("user"):
        st.markdown(full_prompt)

    # 3. Action Detection (The Gatekeeper)
    raw_roll = extract_roll(prompt)
    
    # --- Start Assistant Response ---
    with st.chat_message("assistant"):
        with st.spinner("The DM is thinking..."):
            
            final_response_text = ""
            
            # The narrative config MUST be updated with the final system instruction for the duration of the game
            final_narrative_config = GenerateContentConfig(
                system_instruction=st.session_state["final_system_instruction"]
            )
            
            # =========================================================================
            # A) LOGIC CHECK (IF A ROLL IS DETECTED)
            # =========================================================================
            if raw_roll is not None:
                st.info(f"Skill Check Detected! Player {current_player_name} roll: {raw_roll}")
                
                logic_prompt = f"""
                RESOLVE A PLAYER ACTION:
                1. Character Stats (JSON): {json.dumps(active_char)}
                2. Player Action: "{prompt}"
                3. Task: Determine the appropriate attribute (e.g., Dexterity) and set a reasonable Difficulty Class (DC 10-20). 
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
                    
                    # Display the mechanical result
                    st.toast(f"Result: {skill_check_outcome['outcome_result']} (Roll: {skill_check_outcome['total_roll']} vs DC: {skill_check_outcome['difficulty_class']})")
                    
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
                # Use the entire conversation history (including the final prompt/JSON for continuity)
                narrative_response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=get_api_contents(st.session_state["history"]),
                    config=final_narrative_config
                )
                final_response_text = narrative_response.text
                
            except Exception as e:
                final_response_text = f"Narrative API Error. The system may need to be restarted: {e}"


            # 4. Display the DM's final response
            st.markdown(final_response_text)

            # 5. Update history with the DM's final response (if successful)
            if not final_response_text.startswith("Narrative API Error"):
                st.session_state["history"].append({"role": "assistant", "content": final_response_text})
