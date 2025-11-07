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
}

# --- System Instruction Template ---
# Uses placeholders for setting and genre
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

# Define Skill Check Schema (Kept for completeness, though config is needed for full logic)
class SkillCheckResolution(BaseModel):
    """Structured data for resolving a single player action."""
    action: str = Field(description="The action the player attempted.")
    attribute_used: str = Field(description="The core attribute used for the check.")
    difficulty_class: int = Field(description="The DC set by the DM/Gemini.")
    player_d20_roll: int = Field(description="The raw D20 roll the player provided.")
    attribute_modifier: int = Field(description="The modifier used in the calculation.")
    total_roll: int = Field(description="The calculated result.")
    outcome_result: str = Field(description="The result.")
    hp_change: int = Field(description="Damage taken or health gained. Default 0.", default=0)
    consequence_narrative: str = Field(description="A brief description of the immediate mechanical consequence.")

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

def create_new_character(setting, genre):
    """Function to call the API and create a character JSON."""
    
    # 1. Update the System Instruction with the user's choices
    final_system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        setting=setting,
        genre=genre,
        player_count=1 # Simplified for now
    )
    
    # 2. Define the character creation prompt
    creation_prompt = f"""
    Based on the setting: {setting} and the genre: {genre}, create a starting character.
    The character should be balanced, attribute modifiers should range from -1 to +3, starting HP should be 20, and Morale/Sanity must start at 100.
    Fill in ALL fields in the required JSON schema.
    """

    with st.spinner(f"Creating a survivor for {genre}..."):
        try:
            # We use the narrative config logic here but point the instruction to the dynamic one
            temp_config = GenerateContentConfig(
                system_instruction=final_system_instruction
            )
            
            char_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=creation_prompt,
                config=character_creation_config
            )
            char_data = json.loads(char_response.text)

            # Store the final system instruction for the rest of the game session
            st.session_state["final_system_instruction"] = final_system_instruction
            
            # Store the character in the dictionary under its name
            st.session_state["characters"][char_data['name']] = char_data
            st.session_state["current_player"] = char_data['name']
            
            # Start history with the DM's introduction
            st.session_state["history"].append({"role": "assistant", "content": f"Welcome, {char_data['name']}! Your journey begins in the {setting} world of {genre}. What is your first move?"})

        except Exception as e:
            st.error(f"Character creation failed: {e}. Please check the logs.")


# Helper function to extract a potential roll
def extract_roll(text):
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

selected_setting = st.sidebar.selectbox("Choose Setting", list(SETTINGS_OPTIONS.keys()), disabled=bool(st.session_state["current_player"]))
selected_genre = st.sidebar.selectbox("Choose Genre", SETTINGS_OPTIONS[selected_setting], disabled=bool(st.session_state["current_player"]))


st.sidebar.header("Active Player Sheet")
active_char = st.session_state["characters"].get(st.session_state["current_player"])

if active_char:
    st.sidebar.markdown(f"**Name:** {active_char['name']}")
    st.sidebar.markdown(f"**Class:** {active_char['race_class']}")
    st.sidebar.markdown(f"**HP:** {active_char['current_hp']}")
    st.sidebar.markdown(f"**Sanity:** {active_char['morale_sanity']}")
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Inventory:** " + ", ".join(active_char['inventory']))
else:
    st.sidebar.write("Start a new character to begin the game!")
    with st.sidebar:
        st.button("Start New Character", on_click=lambda: create_new_character(selected_setting, selected_genre))


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
    
    # 2. Add user message to display and history
    st.session_state["history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 3. Action Detection (The Gatekeeper)
    raw_roll = extract_roll(prompt)
    
    # --- Start Assistant Response ---
    with st.chat_message("assistant"):
        with st.spinner("The DM is thinking..."):
            
            final_response_text = ""
            
            # Update narrative config for the API call using the final instruction template
            final_narrative_config = GenerateContentConfig(
                system_instruction=st.session_state["final_system_instruction"]
            )
            
            # =========================================================================
            # A) LOGIC CHECK (IF A ROLL IS DETECTED)
            # =========================================================================
            if raw_roll is not None:
                st.info(f"Skill Check Detected! Player roll: {raw_roll}")
                
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
                    The player's last risky action was RESOLVED. The EXACT JSON outcome was: {json.dumps(skill_check_outcome)}.
                    1. Narrate the vivid, descriptive consequence of this result.
                    2. Update the scene based on the outcome and ask the player what they do next.
                    """
                    
                    # Add the JSON resolution and follow-up prompt to history for the final narrative call
                    st.session_state["history"].append({"role": "assistant", "content": f"//Mechanics: {json.dumps(skill_check_outcome)}//"})
                    st.session_state["history"].append({"role": "user", "content": follow_up_prompt})

                except Exception as e:
                    # Fallback if the JSON parsing fails
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
