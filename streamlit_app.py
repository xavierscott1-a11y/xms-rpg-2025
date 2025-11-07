# Install the official Google GenAI SDK for Python
!pip install -q -U google-genai

import os
from google.colab import userdata
from google import genai

# Retrieve the key from the Colab Secrets manager
GEMINI_API_KEY = userdata.get('GEMINI_API_KEY')

# Create the Gemini client object
client = genai.Client(api_key=GEMINI_API_KEY)

print("Gemini Client is ready!")

# System Instruction: The core rules and persona for the Dungeon Master

system_instruction = """
You are the ultimate Dungeon Master (DM) and Storyteller.

1. Persona and Tone:
* You are an impartial, imaginative, and highly engaging narrator.
* Your tone should match the chosen setting (e.g., gritty and desperate for post-apocalypse).
* You control all Non-Player Characters (NPCs) and the environment.

2. Game Rules (TTRPG Logic):
* The game is for 1-4 players.
* All checks use a D20 roll plus the relevant attribute modifier.
* Difficulty Class (DC) Scale:
    * Low Risk (DC 5): Simple tasks.
    * Medium Risk (DC 10-12): Standard challenges.
    * High Risk (DC 15-20): Challenging feats (e.g., jumping a wide gap).
    * Extreme Risk (DC 20+): Near-impossible feats.
* You must resolve success or failure by comparing (D20 + Modifier) against the DC.
* Critical Success (Natural 20): The attempt succeeds with an extraordinary benefit.
* Critical Failure (Natural 1): The attempt fails catastrophically.

3. Output Format:
* Your response must always begin with a vivid narrative description.
* Do NOT include any JSON output yet. We will implement that later.
* Present clear choices or ask the player what they do next at the end of your turn.

4. Initial Setup Task:
* The user will give you a Setting (e.g., "post-apocalypse").
* You must immediately provide three unique Genre/Thematic options based on that setting.
"""
# Configure the model to use the system instruction
config = genai.types.GenerateContentConfig(
    system_instruction=system_instruction
)

# Choose the model (Flash is fast and cost-effective)
model_name = 'gemini-2.5-flash'

# The player's first prompt, asking for setting options
first_prompt = "I want to start a game. The setting is post-apocalypse."

# Generate the content
response = client.models.generate_content(
    model=model_name,
    contents=first_prompt,
    config=config
)

# Print the DM's response
print(response.text)

from pydantic import BaseModel, Field
from typing import List

# 1. Define the Character Sheet Structure using Pydantic
# This is the blueprint for the character data
class CharacterSheet(BaseModel):
    """A standard character sheet for the RPG game."""
    name: str = Field(description="The player's chosen name.")
    race_class: str = Field(description="The character's core identity, e.g., 'Wasteland Scavenger' or 'Cybernetic Street Sam'.")
    
    # Core Attributes/Modifiers
    str_mod: int = Field(description="Strength Modifier, used for melee and physical actions.")
    dex_mod: int = Field(description="Dexterity Modifier, used for agility, dodging, and stealth.")
    con_mod: int = Field(description="Constitution Modifier, used for health and endurance checks.")
    int_mod: int = Field(description="Intelligence Modifier, used for knowledge, technical skills, and investigation.")
    wis_mod: int = Field(description="Wisdom Modifier, used for perception, survival, and intuition.")
    cha_mod: int = Field(description="Charisma Modifier, used for persuasion, deception, and leadership.")
    
    current_hp: int = Field(description="The character's starting health/hit points (a number like 15 or 20).")
    inventory: List[str] = Field(description="A list of 3-5 starting major gear items, weapons, and key equipment.")
    experience: int = Field(description="Starting experience points (always 0).")
    # 2. Configure the Model to return a JSON object that matches the Pydantic schema
# We use the pydantic schema directly as the response schema for Gemini.
character_creation_config = genai.types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)

# Assuming you chose the "Mutant Survival" genre from a Post-Apocalypse setting
chosen_genre = "Mutant Survival"

creation_prompt = f"""
Based on the setting: Post-Apocalypse and the genre: {chosen_genre}, create a starting character.
The character should be balanced and all attribute modifiers should range between -1 and +3.
Fill in all fields in the required JSON schema.
"""

# Generate the content using the JSON configuration
print(f"DM Prompt: {creation_prompt}")

character_response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=creation_prompt,
    config=character_creation_config
)

# Print the resulting JSON character sheet
print("\n--- Generated Character Sheet (JSON) ---")
print(character_response.text)

# We can even verify it by turning it into a Python object:
import json
character_data = json.loads(character_response.text)
print("\n--- Python Object Verification ---")
print(f"Character Name: {character_data['name']}")
print(f"Dexterity Modifier: +{character_data['dex_mod']}")
print(f"Starting HP: {character_data['current_hp']}")

from pydantic import BaseModel, Field
from typing import Optional

# 1. Define the Skill Check Resolution Structure
class SkillCheckResolution(BaseModel):
    """Structured data for resolving a single player action."""
    action: str = Field(description="The action the player attempted (e.g., 'Jumping a rooftop').")
    attribute_used: str = Field(description="The core attribute used for the check (e.g., 'Dexterity', 'Strength').")
    difficulty_class: int = Field(description="The DC set by the DM/Gemini based on risk (e.g., 5, 12, 20).")
    
    # The actual roll and calculation results
    player_d20_roll: int = Field(description="The raw D20 roll generated by the player (a number 1 to 20).")
    attribute_modifier: int = Field(description="The modifier from the character sheet (e.g., -1, 0, +2).")
    total_roll: int = Field(description="The calculated result: player_d20_roll + attribute_modifier.")
    
    # Final outcome
    outcome_result: str = Field(description="The result: 'Success', 'Failure', 'Critical Success', or 'Critical Failure'.")
    hp_change: int = Field(description="If negative, damage taken; if positive, health gained. Default 0.", default=0)
    
    # Narrative for the consequence (brief)
    consequence_narrative: str = Field(description="A brief description of the immediate physical consequence (e.g., 'Sprained ankle,' or 'Landed perfectly').")
    # 2. Configure the Model to return a JSON object that matches the SkillCheckResolution schema
skill_check_config = genai.types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=SkillCheckResolution,
)

# --- SIMULATE INPUT DATA ---
# This is where your app would retrieve the character JSON from its database/storage.
# NOTE: Replace the values below with the actual JSON data generated in Step 4 for accuracy!
# For this example, we'll assume a Dexterity Modifier of +2.

player_stats_json = """
{
  "name": "Rico",
  "race_class": "Wasteland Scavenger",
  "str_mod": 1,
  "dex_mod": 2,  # IMPORTANT: This stat is what the DM will use!
  "con_mod": 0,
  "int_mod": 1,
  "wis_mod": -1,
  "cha_mod": 0,
  "current_hp": 20,
  "inventory": ["Rusty Pistol", "Repair Kit", "Can of Beans"],
  "experience": 0
}
"""

# The player's simulated input: the action and the raw D20 roll
player_action = "I try to jump across the wide, broken bridge gap. I roll an 11."
# The DM (Gemini) must determine this is a High Risk Dexterity check (DC 15-20).
# Total Roll will be: 11 (Roll) + 2 (Dex Mod) = 13.

# --- GENERATE THE RESULT ---

skill_check_prompt = f"""
RESOLVE A PLAYER ACTION:
1. Character Stats (for reference): {player_stats_json}
2. Player Action: {player_action}
3. The jump is a High Risk action. Determine the appropriate DC and the attribute used.
4. Calculate the result using the player's roll (11) and the correct modifier from the stats.
5. Return ONLY the JSON result following the SkillCheckResolution schema.
"""

# Generate the content using the JSON configuration
print(f"Player Input: {player_action}\n")

check_response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=skill_check_prompt,
    config=skill_check_config
)

# Print the resulting JSON skill check resolution
print("\n--- Skill Check Resolution (JSON) ---")
print(check_response.text)

# --- 1. Re-defining Necessary Imports and Schemas ---
from pydantic import BaseModel, Field
from typing import List, Optional
# Ensure all necessary types are imported
from google.genai.types import Content, Part, GenerateContentConfig
import json

# Assuming client and system_instruction are defined in prior cells.
# If they are not, you must run those cells first:
# client = genai.Client(api_key=GEMINI_API_KEY)
# system_instruction = "..." # Your DM rules text

# Re-define the Skill Check Schema (from Step 5a)
class SkillCheckResolution(BaseModel):
    action: str = Field(description="The action the player attempted.")
    attribute_used: str = Field(description="The core attribute used for the check (e.g., 'Dexterity').")
    difficulty_class: int = Field(description="The DC set by the DM/Gemini.")
    player_d20_roll: int = Field(description="The raw D20 roll generated by the player (1-20).")
    attribute_modifier: int = Field(description="The modifier from the character sheet.")
    total_roll: int = Field(description="The calculated result: roll + modifier.")
    outcome_result: str = Field(description="The result: 'Success', 'Failure', 'Critical Success', or 'Critical Failure'.")
    hp_change: int = Field(description="Damage taken or health gained. Default 0.", default=0)
    consequence_narrative: str = Field(description="A brief description of the immediate consequence.")

# Re-define the Configurations
skill_check_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=SkillCheckResolution,
)

narrative_config = GenerateContentConfig(
    system_instruction=system_instruction
)

# --- 2. SIMULATE INPUT DATA ---
player_stats_json = """
{
  "name": "Rico",
  "race_class": "Wasteland Scavenger",
  "dex_mod": 2, 
  "current_hp": 20
}
"""

# The player's simulated input
player_action_risky = "I attempt the high-risk jump. I roll a 17."
initial_scene_response = "DM Narrates the scene here: The jump is dizzying..."

# **FIX APPLIED HERE:** Use Part(text=...) which is the explicit, non-ambiguous constructor.
user_initial_text = "Start game. Character: " + player_stats_json

# Create the full Conversation History
history = [
    # User's initial prompt and character info
    Content(role="user", parts=[Part(text=user_initial_text)]),
    # DM's initial narrative response
    Content(role="model", parts=[Part(text=initial_scene_response)])
]

print("Starting Full Game Loop Test...")
print(f"Player Action: {player_action_risky}")


# --- 3. LOGIC CALL (JSON RESOLUTION) ---

skill_check_prompt_logic = f"""
RESOLVE A PLAYER ACTION:
1. Character Stats: {player_stats_json}
2. Player Action: {player_action_risky}
3. Task: The jump is High Risk. Set the DC at 18. Calculate result (Roll 17 + Dex Mod +2).
4. Return ONLY the JSON object following the SkillCheckResolution schema.
"""

logic_call_response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=skill_check_prompt_logic,
    config=skill_check_config
)

# Parse the JSON outcome
skill_check_outcome = json.loads(logic_call_response.text)
print("\n--- JSON Resolution ---")
print(json.dumps(skill_check_outcome, indent=2))


# --- 4. NARRATIVE CALL (CONSEQUENCE) ---

consequence_prompt_narrative = f"""
The player's last risky action was RESOLVED. The exact JSON outcome was: {json.dumps(skill_check_outcome)}.

1. Narrate the vivid, descriptive consequence of this result (Total Roll {skill_check_outcome['total_roll']} against DC {skill_check_outcome['difficulty_class']}).
2. Update the scene based on this outcome (Failure).
3. End by asking the player what they do next.
"""

consequence_response = client.models.generate_content(
    model='gemini-2.5-flash',
    # Pass the history list and the new prompt
    contents=history + [Content(role="user", parts=[Part(text=consequence_prompt_narrative)])],
    config=narrative_config
)

print("\n--- Narrative Consequence ---")
print(consequence_response.text)

# --- 1. Define the Image Prompt ---
image_prompt_text = """
A post-apocalyptic scene showing a lone scavenger named Rico clinging to the sharp, broken edge of a skyscraper rooftop. He has missed the jump, and his backpack is tearing against the concrete. The sky is dark with smog, and rusty debris litters the ground far below. Stylized like a graphic novel.
"""

# --- 2. Generate the Image ---
print(f"Requesting image for: {image_prompt_text[:80]}...")

image_response = client.models.generate_images(
    model='imagen-3.0-generate-002',  # Image generation model
    prompt=image_prompt_text,
    config=dict(
        number_of_images=1,
        output_mime_type="image/jpeg",
        aspect_ratio="16:9"
    )
)

from IPython.display import Image, display

# --- 3. Display the Generated Image ---

if image_response.generated_images:
    image_data = image_response.generated_images[0]
    
    if image_data.image.image_bytes:
        img = Image(data=image_data.image.image_bytes)
        print("Image successfully generated and displayed below:")
        display(img)
    else:
        print("Error: Generated image data was empty.")
else:
    print("Error: No images were generated.")

# System Instruction: The refined core rules and persona for the Dungeon Master

system_instruction = """
You are the ultimate Dungeon Master (DM) and Storyteller, running a detailed, persistent TTRPG for a single player in the **Post-Apocalypse, Mutant Survival** setting.

1. Persona and Tone:
* **Narrative Focus:** Your goal is to create a sense of gritty, desperate immersion. Use vivid sensory details (smell, sound, sight) and descriptive, evocative language. The tone should be tense, unforgiving, and dramatic.
* **Pacing:** Maintain a steady pace. Describe the current scene and the immediate challenge. Always end your turn by asking ONE clear, open-ended question about the player's next move.
* **NPCs:** Give all Non-Player Characters unique, memorable names, and realistic, desperate motivations typical of the wasteland.
* **No Spoilers:** Never reveal mechanics, future plot points, or internal DM calculations.

2. Game Rules (TTRPG Logic):
* **DM Authority:** You are the final judge of all rules. When resolving an action, you must follow this logic:
    1.  Determine the **best Attribute** for the check (e.g., DEX for jumping, INT for scavenging).
    2.  Assign a **Difficulty Class (DC)** based on risk: DC 5 (Trivial), DC 10 (Moderate), DC 15 (Hard), DC 20 (Very Hard).
* **Result Integration:** When a skill check outcome (JSON) is provided to you, you must **vividly integrate that exact result** (Success, Failure, Critical Failure) into the very next narrative scene.

3. Persistence and Memory:
* You must maintain continuity. Remember all current **Character Stats, Inventory, and HP**.
* Remember the **state of the environment** (e.g., "The bridge is broken," "The door is locked").

4. Output Format:
* **Strictly Narrative:** Your output must be pure, flowing narrative text. DO NOT include any JSON, mechanical headings like '## SCENE', or rules text unless you are explicitly asked to resolve a skill check in a separate, targeted call.
"""

# Re-using the narrative config (which now points to the new, enhanced system_instruction)
narrative_config = GenerateContentConfig(
    system_instruction=system_instruction
)

# Final prompt to test the DM's narrative skill and memory
narrative_test_prompt = """
The player, Rico, is now desperately clinging to the crumbling ledge, having failed the jump. The wind is biting cold and his grip is weakening.
Narrate the immediate sense of danger, using sensory language (smell of ozone, sound of distant metallic scraping), and ask him what he does to get out of this immediate predicament.
"""

# The 'history' variable contains the setup and the failed jump.
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=history + [Content(role="user", parts=[Part(text=narrative_test_prompt)])],
    config=narrative_config
)

print("--- DM's Refined Narrative Response ---")
print(response.text)

from pydantic import BaseModel, Field
from typing import List
# FIX: Import GenerateContentConfig directly from the types package
from google.genai.types import GenerateContentConfig

# Define the UPDATED Character Sheet Structure
class CharacterSheet(BaseModel):
    """A standard character sheet for the RPG game, including a Morale/Sanity score."""
    name: str = Field(description="The player's chosen name.")
    race_class: str = Field(description="The character's core identity, e.g., 'Wasteland Scavenger'.")

    # Core Attributes/Modifiers
    str_mod: int = Field(description="Strength Modifier.")
    dex_mod: int = Field(description="Dexterity Modifier.")
    con_mod: int = Field(description="Constitution Modifier.")
    int_mod: int = Field(description="Intelligence Modifier.")
    wis_mod: int = Field(description="Wisdom Modifier.")
    cha_mod: int = Field(description="Charisma Modifier.")

    # Status Fields
    current_hp: int = Field(description="The character's current health/hit points (e.g., 20).")
    morale_sanity: int = Field(description="The character's mental fortitude, starting high (e.g., 100). This score should decrease when exposed to extreme psychological trauma, horror, or fear.")
    
    # Inventory and Experience
    inventory: List[str] = Field(description="A list of 3-5 starting major gear items.")
    experience: int = Field(description="Starting experience points (always 0).")

# FIX APPLIED HERE: Using GenerateContentConfig directly
character_creation_config = GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CharacterSheet,
)
print("CharacterSheet schema updated successfully with Morale/Sanity score!")

# The genre is still set to "Mutant Survival" within the Post-Apocalypse setting.
creation_prompt = """
Based on the setting: Post-Apocalypse and the genre: Mutant Survival, create a starting character.
The character should be balanced, attribute modifiers should range from -1 to +3, starting HP should be around 20, and Morale/Sanity must start at 100.
Fill in ALL fields in the required JSON schema.
"""

# Generate the content using the JSON configuration
print(f"DM Prompt: {creation_prompt}")

character_response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=creation_prompt,
    config=character_creation_config
)

# Print the resulting JSON character sheet
print("\n--- Generated Character Sheet (JSON) ---")
print(character_response.text)

# We can verify the JSON was created correctly
import json
final_character_data = json.loads(character_response.text)

print("\n--- Verification Check ---")
print(f"Name: {final_character_data['name']}")
print(f"Class: {final_character_data['race_class']}")
print(f"Starting Sanity/Morale: {final_character_data['morale_sanity']}")
