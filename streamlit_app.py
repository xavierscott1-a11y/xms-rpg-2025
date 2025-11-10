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
IMPORTANT: Integrate the following user-provided details into the world and character backgrounds:
Setting Details: {custom_setting_description}
---
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
    player_d20_roll: int = Field(description="The raw D20 roll provided.")
    attribute_modifier: int = Field(description="The modifier used in the calculation.")
    total_roll: int = Field(description="The calculated result.")
    outcome_result: str = Field(description="Result: 'Success', 'Failure', 'Critical Success', or 'Critical Failure'.")
    hp_change: int = Field(description="Damage taken or health gained. Default 0.", default=0)
    consequence_narrative: str = Field(description="Brief description of the immediate mechanical consequence.")

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

def create_new_character(setting, genre, player_name, custom_char_desc):
    """Function to call the API and create a character JSON."""
    
    if not player_name or player_name in st.session_state["characters"]:
        st.error("Please enter a unique name for the new character.")
        return

    # 1. Update the System Instruction dynamically
    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=len(st.session_state["characters"]) + 1,
        custom_setting_description=st.session_state['custom_setting_description'] # Pass current setting description
    )
    
    creation_prompt = f"""
    Based on the setting: {setting}, genre: {genre}, and the player's custom background, create a starting character named {player_name}.
    Player's Custom Description: {custom_char_desc}
    The character should be balanced, modifiers should be reasonable, starting HP should be 20, and Morale/Sanity must start at 100.
    Fill in ALL fields in the required JSON schema.
    """

    with st.spinner(f"Creating survivor {player_name} for {genre}..."):
        try:
            temp_config = GenerateContentConfig(
                system_instruction=final_system_instruction
            )
            
            char_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=creation_prompt,
                config=character_creation_config
            )
            char_data = json.loads(char_response.text)
            char_data['name'] = player_name 

            st.session_state["final_system_instruction"] = final_system_instruction
            st.session_state["characters"][player_name] = char_data
            if not st.session_state["current_player"]:
                st.session_state["current_player"] = player_name
            
            st.session_state["history"].append({"role": "assistant", "content": f"Player {player_name} added to the party. Ready for adventure initiation."})
            st.rerun() 

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}. Try a simpler name.")

def extract_roll(text):
    """Helper function to extract a number (1-20) indicating a dice roll."""
    match = re.search(r'\b(roll|rolls|rolled|try|trying|tries)\s+(\d{1,2})\b', text, re.IGNORECASE)
    if match and 1 <= int(match.group(2)) <= 20:
        return int(match.group(2))
    return None

def start_adventure(setting, genre):
    """Function to generate the initial narrative hook."""
    if st.session_state["current_player"] is None:
        st.error("Please create at least one character before starting the adventure!")
        return
        
    intro_prompt = f"""
    The game is about to begin in the {setting}, {genre} world. 
    The setting is defined by: {st.session_state['custom_setting_description']}
    Provide a dramatic and engaging introductory narrative (about 3-4 paragraphs). 
    End by asking the active player, {st.session_state['current_player']}, what they do next.
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
            st.session_state["history"].append({"role": "assistant", "content": response.text})
            st.session_state["adventure_started"] = True 
            st.session_state["page"] = "GAME" # Switch page to Game View
            st.rerun() 

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
        "setting": st.session_state["setup_setting"], 
        "genre": st.session_state["setup_genre"],
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

            st.session_state["__LOAD_DATA__"] = loaded_data
            st.session_state["__LOAD_FLAG__"] = True
            
            st.success("Adventure loaded successfully! Restarting session...")
            st.rerun() 

        except Exception as e:
            st.error(f"Error loading file: {e}. Please ensure the file is valid JSON.")


# --- Check for Staged Load Data (Runs BEFORE Widgets are created) ---
if "__LOAD_FLAG__" in st.session_state and st.session_state["__LOAD_FLAG__"]:
    
    loaded_data = st.session_state["__LOAD_DATA__"]

    st.session_state["history"] = loaded_data["history"]
    st.session_state["characters"] = loaded_data["
