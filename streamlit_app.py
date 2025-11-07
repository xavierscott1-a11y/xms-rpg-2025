import streamlit as st
import os
import json
from google import genai
# We import all necessary types directly to avoid the 'client.types' error
from google.genai.types import Content, Part, GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List, Optional
# --- Configuration (Based on all previous steps) ---

# SECURITY: Loads the key from Streamlit Secrets (GEMINI_API_KEY)
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("API Key not found. Please ensure 'GEMINI_API_KEY' is set in Streamlit Secrets.")
    st.stop()

# Initialize the Gemini Client
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Error initializing Gemini Client: {e}")
    st.stop()

# DM Rules (System Instruction from Step 8)
SYSTEM_INSTRUCTION = """
You are the ultimate Dungeon Master (DM) and Storyteller, running a persistent TTRPG for a single player in the Post-Apocalypse, Mutant Survival setting.
Your goal is to create a sense of gritty, desperate immersion. Use vivid sensory details and maintain a tense tone.
When a skill check outcome (JSON) is provided to you, you must vividly integrate that exact result into the next narrative scene.
Your output must be pure, flowing narrative text. DO NOT include JSON unless specifically asked to perform a check.
"""

# Define Narrative Configuration
narrative_config = GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION
)

# Define Character Sheet Schema (Needs to be defined even if not used explicitly below)
# Note: Full schema attributes are omitted here for brevity, but you would include the full class definition here.
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

# Define Character Creation Configuration
character_creation_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)

# --- Functions ---

def create_new_character():
    """Function to call the API and create a character JSON."""
    creation_prompt = """
    Based on the setting: Post-Apocalypse and the genre: Mutant Survival, create a starting character.
    The character should be balanced, attribute modifiers should range from -1 to +3, starting HP should be 20, and Morale/Sanity must start at 100.
    Fill in ALL fields in the required JSON schema.
    """

    with st.spinner("Rolling up your survivor..."):
        try:
            char_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=creation_prompt,
                config=character_creation_config
            )
            # Load the JSON string into a Python dictionary
            char_data = json.loads(char_response.text)

            # Save the new character data to Streamlit's session state
            st.session_state["character"] = char_data
            st.session_state["history"].append({"role": "assistant", "content": f"Welcome, {char_data['name']}! Your character is ready. What is your first move? The wasteland awaits."})

        except Exception as e:
            st.error(f"Character creation failed: {e}. Ensure the model returned valid JSON.")
            st.session_state["history"].append({"role": "assistant", "content": "Failed to create character. Please try again."})


# --- Streamlit UI Setup ---

st.set_page_config(layout="wide")
st.title("🧙 RPG Storyteller DM (Powered by Gemini)")
st.caption("Post-Apocalypse: Mutant Survival")

# --- Initialize Session State ---
if "history" not in st.session_state:
    st.session_state["history"] = []
if "character" not in st.session_state:
    st.session_state["character"] = None

# --- Sidebar (Character Sheet) ---
st.sidebar.header("Character Sheet")
if st.session_state["character"]:
    st.sidebar.markdown(f"**Name:** {st.session_state['character']['name']}")
    st.sidebar.markdown(f"**Class:** {st.session_state['character']['race_class']}")
    st.sidebar.markdown(f"**HP:** {st.session_state['character']['current_hp']}")
    st.sidebar.markdown(f"**Sanity:** {st.session_state['character']['morale_sanity']}")
    st.sidebar.markdown("**Inventory:** " + ", ".join(st.session_state['character']['inventory']))
else:
    st.sidebar.write("Start a new character to begin the game!")
    # Add the button
    with st.sidebar:
        st.button("Start New Character", on_click=create_new_character)

# --- Main Game Loop Display ---

# Display the conversation history
for message in st.session_state["history"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- User Input and API Call ---
prompt = st.chat_input("What do you do?")

if prompt:
    # 1. Check if character exists before allowing play
    if not st.session_state["character"]:
        st.warning("Please create a character first!")
        # Clear the input so the user can re-enter
        st.stop()

    # 2. Add the user message to the display and history
    st.session_state["history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 3. Call the Gemini API (Simplified Narrative Call for now)
    with st.chat_message("assistant"):
        with st.spinner("The DM is thinking..."):
            # Build the contents list for the API call
            # We must convert the dictionary history to the specific Content/Part format
            contents = []
            for msg in st.session_state["history"]:
                # FIX: Use the reliable Part(text=...) constructor
                contents.append(Content(role=msg["role"], parts=[Part(text=msg["content"])]))

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=narrative_config
            )

            # 4. Display the DM's response
            st.markdown(response.text)

            # 5. Update history with the DM's response
            st.session_state["history"].append({"role": "assistant", "content": response.text})
