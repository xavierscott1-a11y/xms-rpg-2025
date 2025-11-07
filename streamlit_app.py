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


# --- Helper Functions ---

def get_api_contents(history_list):
    """Converts Streamlit history format to API content format."""
    contents = []
    for msg in history_list:
        if msg["content"] and isinstance(msg["content"], str):
            # Map Streamlit's "assistant" role to the Gemini API's required "model" role
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
    """Helper function to extract a number (1-20) indicating a dice roll."""
    # Searches for a number between 1 and 20 near keywords like 'roll' or 'try'
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
        "current_player": st.session_state["current_player"],
        "adventure_started": st.session_state["adventure_started"],
        # Save genre/setting choices for display on load
        "setting": st.session_state["setup_setting"], 
        "genre": st.session_state["setup_genre"],
    }
    
    # Simple (non-persistent) way to store the JSON data in Streamlit's file system for download/upload
    st.session_state["saved_game_json"] = json.dumps(game_state, indent=2)
    st.success("Game state saved to memory. Use the Download button to secure your file!")

def load_game(uploaded_file):
    """Loads game state from an uploaded file."""
    if uploaded_file is not None:
        try:
            bytes_data = uploaded_file.read()
            loaded_data = json.loads(bytes_data)

            # Restore the session state
            st.session_state["history"] = loaded_data["history"]
            st.session_state["characters"] = loaded_data["characters"]
            st.session_state["final_system_instruction"] = loaded_data["system_instruction"]
            st.session_state["current_player"] = loaded_data["current_player"]
            st.session_state["adventure_started"] = loaded_data["adventure_started"]
            
            # Restore settings for display
            st.session_state["setup_setting"] = loaded_data.get("setting", "Post-Apocalypse")
            st.session_state["setup_genre"] = loaded_data.get("genre", "Mutant Survival")
            
            st.success("Adventure successfully loaded!")
            st.rerun()
        except Exception as e:
            st.error(f"Error loading file: {e}. Please ensure the file is valid JSON.")


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
if "new_player_name" not in st.session_state: 
    st.session_state["new_player_name"] = "" 
if "adventure_started" not in st.session_state:
    st.session_state["adventure_started"] = False
if "saved_game_json" not in st.session_state:
    st.session_state["saved_game_json"] = ""


# --- Define the three columns ---
col_settings, col_chat, col_stats = st.columns([2, 5, 3])

game_started = st.session_state["adventure_started"]

# =========================================================================
# LEFT COLUMN (Settings & Controls)
# =========================================================================
with col_settings:
    st.header("Game Setup")

    # Genre selection
    selected_setting = st.selectbox("Choose Setting", list(SETTINGS_OPTIONS.keys()), disabled=game_started, key="setup_setting")
    selected_genre = st.selectbox("Choose Genre", SETTINGS_OPTIONS[selected_setting], disabled=game_started, key="setup_genre")

    st.subheader("Roster")
    
    # Input field for new character name
    if not game_started:
        st.text_input("New Player Name", key="new_player_name_input")
        
        # Character Creation Button
        if st.button("Add Character to Party", disabled=not st.session_state["new_player_name_input"] or game_started):
            create_new_character(selected_setting, selected_genre, st.session_state["new_player_name_input"])
        
        # Display roster summary
        if st.session_state["characters"]:
             st.markdown(f"**Party ({len(st.session_state['characters'])}):** {', '.join(st.session_state['characters'].keys())}")

    # START ADVENTURE BUTTON (Bottom of Left Column)
    st.markdown("---")
    if not game_started and st.session_state["current_player"]:
         st.button("🚀 START ADVENTURE", 
                   on_click=lambda: start_adventure(selected_setting, selected_genre), 
                   type="primary")
    elif game_started:
         st.markdown("Adventure in Progress!")
         
    st.markdown("---")
    st.subheader("Save/Load")
    
    # Save Button
    if st.button("💾 Save Adventure", disabled=not game_started, on_click=save_game):
        pass # Function called on_click
    
    # Download Button (only appears after save_game is run)
    if st.session_state["saved_game_json"]:
         st.download_button(
             label="Download Game File",
             data=st.session_state["saved_game_json"],
             file_name="gemini_rpg_save.json",
             mime="application/json",
         )

    # Load Button/Uploader
    uploaded_file = st.file_uploader("Load Adventure File", type="json")
    if uploaded_file is not None and st.button("Load"):
        load_game(uploaded_file)


# =========================================================================
# RIGHT COLUMN (Active Player Stats)
# =========================================================================
with col_stats:
    st.header("Active Player Stats")
    
    active_char = st.session_state["characters"].get(st.session_state["current_player"])

    if st.session_state["characters"]:
        # Player selector dropdown
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
        
        # Display stats
        if active_char:
            st.subheader(active_char['name'])
            st.markdown(f"**Class:** {active_char['race_class']}")
            st.markdown(f"**HP:** {active_char['current_hp']}")
            st.markdown(f"**Sanity/Morale:** {active_char['morale_sanity']}")
            st.markdown("---")
            st.markdown("**Inventory:** " + ", ".join(active_char['inventory']))
    else:
        st.write("No characters created.")


# =========================================================================
# CENTER COLUMN (Game Chat and Logic)
# =========================================================================
with col_chat:
    st.header("The Story Log")
    
    # Display the conversation history in reverse order (newest on top)
    for message in reversed(st.session_state["history"]):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


    # --- User Input and API Call Logic (Only active when adventure has started) ---
    if game_started:
        prompt = st.chat_input("What do you do?")

        if prompt:
            # 1. Add user message to display and history (with player name prepended)
            current_player_name = st.session_state["current_player"]
            active_char = st.session_state["characters"].get(current_player_name)
            
            full_prompt = f"({current_player_name}'s Turn): {prompt}"
            st.session_state["history"].append({"role": "user", "content": full_prompt})
            with st.chat_message("user"):
                st.markdown(full_prompt)

            # 2. Action Detection (The Gatekeeper)
            raw_roll = extract_roll(prompt)
            
            # --- Start Assistant Response ---
            with st.chat_message("assistant"):
                with st.spinner("The DM is thinking..."):
                    
                    final_response_text = ""
                    
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
