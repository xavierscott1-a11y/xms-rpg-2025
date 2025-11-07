import streamlit as st
import os
import json
import re
from google import genai
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


# --- Helper Functions (No Change) ---
def get_api_contents(history_list):
    """Converts Streamlit history format to API content format."""
    contents = []
    for msg in history_list:
        if msg["content"] and isinstance(msg["content"], str):
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def create_new_character(setting, genre, player_name):
    # ... (function body remains the same as previous step) ...
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

            # Store the character and set the active player if this is the first one
            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            if not st.session_state["current_player"]:
                st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"Player {player_name} added to the party. Ready for adventure initiation."})
            st.rerun() # Rerun to update the player selector

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}. Try a simpler name.")

def extract_roll(text):
    # ... (function body remains the same as previous step) ...
    """Helper function to extract a number (1-20) indicating a dice roll."""
    # Searches for a number between 1 and 20 near keywords like 'roll' or 'try'
    match = re.search(r'\b(roll|rolls|rolled|try|trying|tries)\s+(\d{1,2})\b', text, re.IGNORECASE)
    if match and 1 <= int(match.group(2)) <= 20:
        return int(match.group(2))
    return None

def start_adventure(setting, genre):
    # ... (function body remains the same as previous step) ...
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
            # We use the full final system instruction
            final_narrative_config = GenerateContentConfig(
                system_instruction=st.session_state["final_system_instruction"]
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=intro_prompt,
                config=final_narrative_config
            )
            
            # Reset history and start with the DM's introduction
            st.session_state["history"] = []
            st.session_state["history"].append({"role": "assistant", "content": response.text})
            st.session_state["adventure_started"] = True # Mark the game as started
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
        "current_player": st.
