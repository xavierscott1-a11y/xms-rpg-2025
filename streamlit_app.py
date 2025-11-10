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

# System Instruction Template - Set the core DM rules
SYSTEM_INSTRUCTION_TEMPLATE = """
You are the ultimate Dungeon Master (DM) and Storyteller, running a persistent TTRPG for {player_count} players in the **{setting}, {genre}** setting.
IMPORTANT: Integrate the following user-provided details into the world and character backgrounds:
Setting Details: {custom_setting_description}
---
Game Rules:
1. **Free Actions:** Simple actions like looking around, dropping an item, or shouting a brief warning are **Free Actions** and do not end the player's turn or require a check. Only complex, risky, or time-consuming actions require a skill check.
2. **Combat/Skill Check Display:** After resolving a skill check, you MUST narrate the outcome vividly. The narration should follow a mechanical summary showing the DC vs. the result. Example: "You swing your sword. (Monster AC 12 vs Roll 12 + Mod 4 = 16. Success)"
---
Your tone must match the genre: be immersive, tense, and dramatic.
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
            # Map Streamlit's "assistant" role to the Gemini API's required "model" role
            api_role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(Content(role=api_role, parts=[Part(text=msg["content"])]))
    return contents

def create_new_character_handler(setting, genre, player_name, selected_class, custom_char_desc, difficulty):
    """Function to call the API and create a character JSON."""
    
    # Check if name is provided and unique
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
    Based on the setting: {setting}, genre: {genre}. Create a starting character named {player_name}.
    The character's primary role must be: {selected_class}.
    Player's Custom Description: {custom_char_desc if custom_char_desc else "No specific background details provided. Create a generic background appropriate for the class."}
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

        except Exception as e:
            st.error(f"Character creation failed for {player_name}: {e}. Try again in a moment.")
            st.session_state["history"].append({"role": "assistant", "content": "Failed to create character due to API error. Please try again."})

    # --- FINAL CLEANUP AND RERUN ---
    st.session_state["new_player_name_input_setup_value"] = "" # Clear input helper
    st.session_state["custom_character_description"] = "" # Clear description
    st.rerun() 


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
            st.session_state["history"].append({"role": "assistant", "content": response.text})
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
if "__LOAD_FLAG__" not in st.session_state:
    st.session_state["__LOAD_FLAG__"] = False
if "__LOAD_DATA__" not in st.session_state:
    st.session_state["__LOAD_DATA__"] = None
if "page" not in st.session_state: # New page management flag
    st.session_state["page"] = "SETUP" 
if "custom_setting_description" not in st.session_state:
    st.session_state["custom_setting_description"] = "" 
if "custom_character_description" not in st.session_state:
    st.session_state["custom_character_description"] = "" 
if "new_player_name_input_setup_value" not in st.session_state: # Used to reset input field
    st.session_state["new_player_name_input_setup_value"] = ""


# =========================================================================
# PAGE 1: SETUP VIEW
# =========================================================================

if st.session_state["page"] == "SETUP":
    
    st.header("1. Define Your Campaign World")
    
    col_world_settings, col_world_description = st.columns([1, 2])
    
    with col_world_settings:
        st.subheader("Core Setting")
        selected_setting = st.selectbox("Choose Setting", list(SETTINGS_OPTIONS.keys()), key="setup_setting")
        selected_genre = st.selectbox("Choose Genre", SETTINGS_OPTIONS[selected_setting], key="setup_genre")
        
        # Difficulty selection
        st.subheader("Difficulty")
        selected_difficulty = st.selectbox("Game Difficulty", list(DIFFICULTY_OPTIONS.keys()), key="setup_difficulty")
        st.caption(DIFFICULTY_OPTIONS[selected_difficulty])
        
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
        
        # Class selection dropdown (dynamic based on setting)
        selected_class_list = CLASS_OPTIONS[st.session_state.get('setup_setting', 'Classic Fantasy')]
        selected_class = st.selectbox("Choose Class/Role", selected_class_list, key="setup_class")
        
        # Character Name input uses the session state value for proper resetting
        new_player_name = st.text_input("Character Name", value=st.session_state["new_player_name_input_setup_value"], key="new_player_name_input_setup")
        
        # Display roster summary
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
        if st.session_state["new_player_name_input_setup"]: # ONLY require a name
            create_new_character_handler(
                st.session_state["setup_setting"], 
                st.session_state["setup_genre"], 
                st.session_state["new_player_name_input_setup"],
                st.session_state["setup_class"], # Pass the selected class
                st.session_state["custom_character_description"],
                st.session_state["setup_difficulty"] # Pass the selected difficulty
            )
        else:
            st.error("Please provide a Character Name.")


    st.markdown("---")
    st.header("3. Start Game")
    
    if st.session_state["current_player"]:
        st.success(f"Party ready! {len(st.session_state['characters'])} player(s) created.")
        st.button("🚀 START ADVENTURE", 
                   on_click=lambda: start_adventure(st.session_state["setup_setting"], st.session_state["setup_genre"]), 
                   type="primary")
    else:
        st.warning("Create at least one character to start.")

# =========================================================================
# PAGE 2: GAME VIEW (THREE COLUMNS)
# =========================================================================

elif st.session_state["page"] == "GAME":
    
    # --- Define the three columns ---
    # NOTE: The visual height of the containers is what makes the UI scrollable and separated.
    col_settings, col_chat, col_stats = st.columns([2, 5, 3])

    game_started = st.session_state["adventure_started"]

    # =========================================================================
    # LEFT COLUMN (Settings & Controls)
    # =========================================================================
    with col_settings:
        with st.container(border=True):
            st.header("Game Details")
            st.info(f"**Setting:** {st.session_state.get('setup_setting')} / {st.session_state.get('setup_genre')}")
            st.info(f"**Difficulty:** {st.session_state.get('setup_difficulty')}")
            st.markdown(f"**Details:** {st.session_state.get('custom_setting_description')}")
            st.markdown("---")
            st.subheader("Roster")
            if st.session_state["characters"]:
                st.markdown(f"**Party ({len(st.session_state['characters'])}):** {', '.join(st.session_state['characters'].keys())}")

            # Save/Load Functionality
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

    # =========================================================================
    # RIGHT COLUMN (Active Player Stats)
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
                    final_response_text = narrative_response.text
                    
                except Exception as e:
                    final_response_text = f"Narrative API Error: {e}"


                # 3. Update history with the DM's final response
                if not final_response_text.startswith("Narrative API Error"):
                    st.session_state["history"].append({"role": "assistant", "content": final_response_text})
                
                # Force a final rerun to display the response and clear the input box
                st.rerun()
