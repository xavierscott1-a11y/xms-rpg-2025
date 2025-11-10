import streamlit as st
st.set_page_config(layout="wide")

import json, re, string, random, math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import streamlit.components.v1 as components

# Optional AI narration (kept off by default)
USE_AI_NARRATION_DEFAULT = False
try:
    from google import genai
    from google.genai.types import Content, Part, GenerateContentConfig
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

# =================== Styles ===================
st.markdown("""
<style>
[data-testid="stSidebar"] { width: 540px; min-width: 540px; }
@media (max-width: 1200px) { [data-testid="stSidebar"] { width: 460px; min-width: 460px; } }
section[aria-label="Active Player"] div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.25rem; }
div.continue-bar { margin-top: 0.5rem; }
small.srd-note { opacity: 0.75; display:block; margin-top:1rem; }
hr.slim { border:none; border-top:1px solid #444; margin:6px 0; }
</style>
""", unsafe_allow_html=True)

# =================== Scroll to top helper ===================
def _scroll_to_top():
    components.html("""
        <script>window.parent.scrollTo({ top: 0, behavior: 'smooth' });</script>
    """, height=0)

# =================== Safe setup for AI narration ===================
client = None
if GEMINI_AVAILABLE:
    try:
        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
        if GEMINI_API_KEY:
            client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        client = None

def ai_narrate(history: List[Dict[str,str]], system_instruction: str) -> str:
    """Optional flavor narration—mechanics do NOT depend on AI."""
    if not client:
        return ""
    try:
        cfg = GenerateContentConfig(system_instruction=system_instruction)
        # convert to Gemini format
        contents=[]
        for m in history:
            role = "model" if m["role"]=="assistant" else m["role"]
            contents.append({"role": role, "parts":[{"text": m["content"]}]})
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=contents, config=cfg)
        return getattr(resp, "text", "") or ""
    except Exception as e:
        return f"(Narration error: {e})"

SYSTEM_INSTRUCTION = """You are a dramatic but concise fantasy narrator. 
Keep narration vivid, tense, and responsive to recent mechanics without contradicting them. 
Do not output rules text; focus on story beats and sensory details, and always end with a clear prompt asking what the party does next."""

# =================== Core data & rules (SRD-like) ===================

# Ability modifier container (we’ll keep modifiers rather than full scores)
ABILS = ["str_mod","dex_mod","con_mod","int_mod","wis_mod","cha_mod"]

# Level / XP quick table (Lv1–5 for demo)
LEVEL_TABLE = [
    (1, 0,   2),  # (level, xp_min, proficiency_bonus)
    (2, 300, 2),
    (3, 900, 2),
    (4, 2700,2),
    (5, 6500,3),
]

# Simple class info
CASTING_MOD = {"Wizard":"int_mod","Cleric":"wis_mod"}
MARTIAL_CLASSES = {"Fighter","Barbarian","Rogue","Paladin","Ranger"}  # influences weapon proficiency defaults (simple+martial)
SIMPLE_WEAPON_PROF = {"Wizard","Cleric","Rogue","Barbarian","Fighter","Paladin","Ranger"}
MARTIAL_WEAPON_PROF = {"Fighter","Barbarian","Paladin","Ranger"}

# Canonical caster mapping
CASTER_KEYWORDS = {"wizard":"Wizard","cleric":"Cleric"}
def canonical_class(name: Optional[str]) -> str:
    s = (name or "").lower()
    for k,v in CASTER_KEYWORDS.items():
        if k in s: return v
    return (name or "").strip().title()

# SRD lite items (same as your prior version)
SRD_ITEMS = {
    "dagger":{"type":"weapon","hands":1,"damage":"1d4","properties":["finesse","light","thrown"],"simple":True},
    "shortsword":{"type":"weapon","hands":1,"damage":"1d6","properties":["finesse","light"],"simple":False},
    "longsword":{"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"],"simple":False},
    "rapier":{"type":"weapon","hands":1,"damage":"1d8","properties":["finesse"],"simple":False},
    "battleaxe":{"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"],"simple":False},
    "warhammer":{"type":"weapon","hands":1,"damage":"1d8","properties":["versatile 1d10"],"simple":False},
    "greataxe":{"type":"weapon","hands":2,"damage":"1d12","properties":["heavy","two-handed"],"simple":False},
    "greatsword":{"type":"weapon","hands":2,"damage":"2d6","properties":["heavy","two-handed"],"simple":False},
    "shortbow":{"type":"weapon","hands":2,"damage":"1d6","properties":["two-handed","ammunition","range"],"ranged":True,"simple":True},
    "longbow":{"type":"weapon","hands":2,"damage":"1d8","properties":["heavy","two-handed","ammunition","range"],"ranged":True,"simple":False},
    "shield":{"type":"shield","hands":1,"ac_bonus":2,"properties":["worn in one arm"]},
    "leather armor":{"type":"armor","hands":0,"armor":{"category":"light","base":11,"dex_cap":None}},
    "studded leather":{"type":"armor","hands":0,"armor":{"category":"light","base":12,"dex_cap":None}},
    "chain shirt":{"type":"armor","hands":0,"armor":{"category":"medium","base":13,"dex_cap":2}},
    "scale mail":{"type":"armor","hands":0,"armor":{"category":"medium","base":14,"dex_cap":2}},
    "half plate":{"type":"armor","hands":0,"armor":{"category":"medium","base":15,"dex_cap":2}},
    "chain mail":{"type":"armor","hands":0,"armor":{"category":"heavy","base":16,"dex_cap":0}},
    "splint":{"type":"armor","hands":0,"armor":{"category":"heavy","base":17,"dex_cap":0}},
    "plate":{"type":"armor","hands":0,"armor":{"category":"heavy","base":18,"dex_cap":0}},
    "boots":{"type":"gear","hands":0,"properties":["footwear"]},
    "ring":{"type":"gear","hands":0,"properties":["jewelry"]},
    "amulet":{"type":"gear","hands":0,"properties":["neckwear"]},
    "helm":{"type":"gear","hands":0,"properties":["headwear"]},
}
ALIASES = {
    "leather":"leather armor","leather armour":"leather armor",
    "studded leather armor":"studded leather","studded armour":"studded leather",
    "chainmail":"chain mail","chain mail armor":"chain mail","chainmail armor":"chain mail",
    "mail":"chain mail","half-plate":"half plate","breastplate":"scale mail",
    "long sword":"longsword","short sword":"shortsword","battle axe":"battleaxe","war hammer":"warhammer",
    "great sword":"greatsword","great axe":"greataxe","buckler":"shield","helmet":"helm",
    "chain shirt armor":"chain shirt"
}
DROP_WORDS = set("well-made fine sturdy rusty old new decorated engraved masterwork +1 +2 +3 +4 +5 armor armour of the".split())

def _tok(s:str)->List[str]:
    s=(s or "").lower()
    s=s.translate(str.maketrans("","",string.punctuation))
    return [w for w in s.split() if w and w not in DROP_WORDS]

def canonicalize_item_name(name:str)->Optional[str]:
    if not name: return None
    low=name.strip().lower()
    if low in SRD_ITEMS: return low
    if low in ALIASES and ALIASES[low] in SRD_ITEMS: return ALIASES[low]
    tokens=_tok(low); joined=" ".join(tokens)
    if joined in ALIASES and ALIASES[joined] in SRD_ITEMS: return ALIASES[joined]
    if joined in SRD_ITEMS: return joined
    # fuzzy subset
    name_t=set(tokens); best=None; best_len=-1
    for k in SRD_ITEMS:
        kt=set(_tok(k))
        if kt and kt.issubset(name_t):
            l=len(" ".join(kt))
            if l>best_len: best=k; best_len=l
    return best

def item_stats(name:str)->Optional[Dict]:
    c=canonicalize_item_name(name)
    return SRD_ITEMS.get(c) if c else None

SLOTS = ["right_arm","left_arm","body","feet","right_hand","left_hand","neck","head"]
SLOT_LABEL = {"right_arm":"Right Arm","left_arm":"Left Arm","body":"Body","feet":"Feet",
              "right_hand":"Right Hand","left_hand":"Left Hand","neck":"Neck","head":"Head"}

def ensure_equipped(char:Dict):
    char.setdefault("equipped",{})
    for s in SLOTS: char["equipped"].setdefault(s, None)

def equip(char:Dict, slot:str, item:str):
    ensure_equipped(char)
    stats=item_stats(item) or {}
    # un-equip same item elsewhere
    norm=(canonicalize_item_name(item) or item).lower()
    for s in SLOTS:
        eq=char["equipped"].get(s)
        if eq and (canonicalize_item_name(eq["item"]) or eq["item"]).lower()==norm:
            char["equipped"][s]=None
    entry={"item":item,"stats":stats}
    char["equipped"][slot]=entry
    # handle 2h weapon occupying both arms & no shield
    if stats.get("type")=="weapon" and stats.get("hands",1)==2:
        other="left_arm" if slot=="right_arm" else "right_arm"
        char["equipped"][other]=entry
        for s in ("left_arm","right_arm"):
            eq=char["equipped"].get(s)
            if eq and eq is not entry and eq.get("stats",{}).get("type")=="shield":
                char["equipped"][s]=None

def unequip(char:Dict, slot:str):
    ensure_equipped(char)
    char["equipped"][slot]=None

def ac_calc(char:Dict)->Tuple[int,str]:
    ensure_equipped(char)
    dex=int(char.get("dex_mod",0))
    base=10; dex_add=dex; parts=[]
    armor=char["equipped"].get("body")
    if armor and armor.get("stats",{}).get("type")=="armor":
        a=armor["stats"]["armor"]; base=a["base"]
        cap=a["dex_cap"]; 
        if cap is None: parts=[f"{base} (Armor)","+DEX"]; dex_add=dex
        elif cap>0: parts=[f"{base} (Armor)",f"+DEX (max {cap})"]; dex_add=min(dex,cap)
        else: parts=[f"{base} (Armor)"]; dex_add=0
    else:
        parts=["10 (Base)","+DEX"]
    shield=0
    for arm in ("left_arm","right_arm"):
        eq=char["equipped"].get(arm)
        if eq and eq.get("stats",{}).get("type")=="shield":
            shield=max(shield,int(eq["stats"].get("ac_bonus",0)))
    if shield: parts.append(f"+Shield {shield}")
    total=base+dex_add+shield
    return total," ".join(parts)

def prof_bonus_for_xp(xp:int)->int:
    pb=2
    for lvl, xp_min, p in LEVEL_TABLE:
        if xp>=xp_min: pb=p
    return pb

def level_for_xp(xp:int)->int:
    lvl=1
    for L, xp_min, _ in LEVEL_TABLE:
        if xp>=xp_min: lvl=L
    return lvl

def roll(dice:str)->int:
    # supports "XdY[+Z]" and single "dY"
    dice=dice.lower().strip()
    m=re.match(r'(\d+)?d(\d+)([+-]\d+)?$', dice)
    if not m:
        # try plain int
        try: return int(dice)
        except: return 0
    n=int(m.group(1) or 1); sides=int(m.group(2)); mod=int(m.group(3) or 0)
    return sum(random.randint(1,sides) for _ in range(n))+mod

def dm_attack_bonus(char:Dict, weapon_stats:Dict)->int:
    cls=canonical_class(char.get("race_class"))
    pb=prof_bonus_for_xp(int(char.get("experience",0)))
    # ability: finesse/ranged=DEX, else STR
    finesse = "finesse" in (weapon_stats.get("properties") or [])
    ranged  = bool(weapon_stats.get("ranged"))
    abil = "dex_mod" if (finesse or ranged) else "str_mod"
    mod = int(char.get(abil,0))
    # proficiency?
    simple_ok = weapon_stats.get("simple", False)
    martial_ok = not simple_ok
    prof = False
    if cls in SIMPLE_WEAPON_PROF and simple_ok: prof=True
    if cls in MARTIAL_WEAPON_PROF and martial_ok: prof=True
    return mod + (pb if prof else 0), abil

def dm_damage_roll(weapon_stats:Dict, abil_mod:int)->int:
    dmg=roll(weapon_stats.get("damage","1"))
    # STR to melee damage; DEX if finesse (house rule common)
    finesse="finesse" in (weapon_stats.get("properties") or [])
    ranged=bool(weapon_stats.get("ranged"))
    add = abil_mod if (finesse or not ranged) else 0
    return max(1, dmg + add)

# =================== Spell system (Lv1 demo effects) ===================

WIZARD_L1 = ["Magic Missile","Shield","Mage Armor","Burning Hands","Thunderwave","Detect Magic","Identify","Grease","Sleep","Chromatic Orb"]
CLERIC_L1 = ["Cure Wounds","Bless","Shield of Faith","Guiding Bolt","Healing Word","Detect Evil and Good","Sanctuary","Inflict Wounds","Protection from Evil and Good"]

CLASS_SPELLS = {"Wizard": {"1": WIZARD_L1}, "Cleric": {"1": CLERIC_L1}}
CLASS_SLOTS  = {"Wizard": {"1": 2}, "Cleric":{"1": 2}}

def class_spell_list(cls:str, level:int=1)->List[str]:
    return CLASS_SPELLS.get(cls,{}).get(str(level),[])

def ensure_spell_fields(char:Dict):
    cls=canonical_class(char.get("race_class"))
    char.setdefault("spells_known",[])
    char.setdefault("spells_prepared",[])
    char.setdefault("spell_slots",{})
    if cls in CLASS_SLOTS and "1" not in char["spell_slots"]:
        m = CLASS_SLOTS[cls]["1"]
        char["spell_slots"]["1"]={"max":m,"current":m}
    if not char["spells_known"] and cls in CLASS_SPELLS:
        char["spells_known"]=class_spell_list(cls)[:4]
    if not char["spells_prepared"] and cls in CLASS_SPELLS:
        limit = 1 + max(0, int(char.get(CASTING_MOD.get(cls,"int_mod"),0)))
        base = char["spells_known"][:limit] or class_spell_list(cls)[:limit]
        char["spells_prepared"]=base

def spell_save_dc(char:Dict)->int:
    cls=canonical_class(char.get("race_class"))
    pb=prof_bonus_for_xp(int(char.get("experience",0)))
    mod=int(char.get(CASTING_MOD.get(cls,"int_mod"),0))
    return 8 + pb + mod

def consume_slot(char:Dict, level:int=1)->bool:
    slots=char.get("spell_slots",{}).get(str(level))
    if not slots: return False
    if slots["current"]<=0: return False
    slots["current"]-=1
    return True

# --- Spell effects (very compact SRD-like summaries; no proprietary text) ---
def do_spell_effect(state:Dict, caster:Dict, spell:str, target_name:str=""):
    """Mutates state (HP etc.). Returns (log_lines)."""
    logs=[]
    cname=caster["name"]
    cls=canonical_class(caster.get("race_class"))
    if spell not in caster.get("spells_prepared",[]):
        return [f"{cname} tries to cast {spell}, but it isn't prepared."]
    if not consume_slot(caster,1):
        return [f"{cname} has no spell slots left."]

    dc=spell_save_dc(caster)
    pb = prof_bonus_for_xp(int(caster.get("experience",0)))
    cast_mod = int(caster.get(CASTING_MOD.get(cls,"int_mod"),0))

    # Helper to find combatant by name
    def get_cbt(name:str)->Optional[Dict]:
        for c in state["encounter"]["combatants"]:
            if c["name"].lower()==name.lower(): return c
        return None

    # Effects
    if spell=="Cure Wounds":
        amt = roll("1d8") + max(0, cast_mod)
        tgt = get_cbt(target_name) or caster
        if tgt.get("dead"): return [f"{cname} casts Cure Wounds, but {tgt['name']} is dead."]
        tgt["current_hp"] = min(tgt["max_hp"], tgt["current_hp"] + amt)
        logs.append(f"{cname} casts Cure Wounds on {tgt['name']} and restores {amt} HP.")
    elif spell=="Magic Missile":
        # 3 darts, 1d4+1 each; let user choose single target for simplicity
        darts = [roll("1d4")+1 for _ in range(3)]
        dmg=sum(darts)
        tgt=get_cbt(target_name) or None
        if not tgt: return [f"{cname} casts Magic Missile, but no valid target is selected."]
        tgt["current_hp"]-=dmg
        logs.append(f"{cname} casts Magic Missile at {tgt['name']} for {dmg} force damage (auto-hit).")
        if tgt["current_hp"]<=0: handle_ko_or_death(tgt, logs)
    elif spell=="Burning Hands":
        # Simple: one target makes DEX save; fail: 3d6, success half
        dmg_full = sum(roll("1d6") for _ in range(3))
        tgt=get_cbt(target_name) or None
        if not tgt: return [f"{cname} casts Burning Hands, but no valid target is selected."]
        save_roll = random.randint(1,20) + int(tgt.get("dex_mod",0))
        if save_roll >= dc:
            dmg = math.floor(dmg_full/2)
            res="succeeds"
        else:
            dmg = dmg_full
            res="fails"
        tgt["current_hp"]-=dmg
        logs.append(f"{cname} casts Burning Hands; {tgt['name']} {res} DEX save (DC {dc}) and takes {dmg} fire damage.")
        if tgt["current_hp"]<=0: handle_ko_or_death(tgt, logs)
    elif spell=="Bless":
        # Simple concentration buff: +1d4 to attack rolls for up to 3 allies this encounter
        # We’ll mark a flag on party side; resets at end of encounter.
        state["encounter"].setdefault("bless", set())
        # auto-applies to caster + 2 others you choose minimally—here: whole party up to 3
        party = [c for c in state["encounter"]["combatants"] if c.get("is_player")]
        chosen = [c["name"] for c in party[:3]]
        state["encounter"]["bless"] = set(chosen)
        logs.append(f"{cname} casts Bless on {', '.join(chosen)}. They add +1d4 to attack rolls while Bless lasts.")
    else:
        logs.append(f"{cname} casts {spell}. (Narrative effect not automated.)")
    return logs

# =================== Monsters (tiny SRD-ish sample) ===================
MONSTERS = {
    "Goblin":  {"ac":15,"hp":7,"str_mod":-1,"dex_mod":2,"con_mod":0,"int_mod":0,"wis_mod":0,"cha_mod":-1,
                "attack_bonus":4,"damage":"1d6+2","speed":30},
    "Skeleton":{"ac":13,"hp":13,"str_mod":0,"dex_mod":2,"con_mod":0,"int_mod":-2,"wis_mod":0,"cha_mod":-2,
                "attack_bonus":4,"damage":"1d6+2","speed":30},
    "Bandit":  {"ac":12,"hp":11,"str_mod":0,"dex_mod":1,"con_mod":0,"int_mod":0,"wis_mod":0,"cha_mod":0,
                "attack_bonus":3,"damage":"1d6+1","speed":30},
    "Wolf":    {"ac":13,"hp":11,"str_mod":2,"dex_mod":2,"con_mod":1,"int_mod":-4,"wis_mod":1,"cha_mod":-2,
                "attack_bonus":4,"damage":"2d4+2","speed":40},
}

# =================== Encounter helpers ===================

def new_combatant_from_char(c:Dict)->Dict:
    ac,_=ac_calc(c)
    return {
        "is_player": True,
        "name": c["name"],
        "ac": ac,
        "max_hp": int(c.get("current_hp",20)),
        "current_hp": int(c.get("current_hp",20)),
        "death_saves": {"success":0,"fail":0},
        "dead": False,
        "dex_mod": int(c.get("dex_mod",0)),
        "str_mod": int(c.get("str_mod",0)),
        "con_mod": int(c.get("con_mod",0)),
        "int_mod": int(c.get("int_mod",0)),
        "wis_mod": int(c.get("wis_mod",0)),
        "cha_mod": int(c.get("cha_mod",0)),
        "src_ref": c["name"],
    }

def new_monster(name:str, template:str)->Dict:
    m=MONSTERS[template]
    return {
        "is_player": False,
        "name": name,
        "ac": m["ac"],
        "max_hp": m["hp"],
        "current_hp": m["hp"],
        "death_saves":{"success":0,"fail":0},
        "dead": False,
        "dex_mod": m["dex_mod"],
        "str_mod": m["str_mod"],
        "con_mod": m["con_mod"],
        "int_mod": m["int_mod"],
        "wis_mod": m["wis_mod"],
        "cha_mod": m["cha_mod"],
        "attack_bonus": m["attack_bonus"],
        "damage": m["damage"],
        "src_ref": template,
    }

def roll_initiative(cbt:Dict)->int:
    return random.randint(1,20)+int(cbt.get("dex_mod",0))

def begin_encounter(state:Dict):
    party = [new_combatant_from_char(ch) for ch in state["characters"].values()]
    state["encounter"] = {
        "active": True,
        "round": 1,
        "turn_index": 0,
        "combatants": party,   # monsters will be appended
        "initiative": [],
        "bless": set(),
        "log": [],
        "xp_reward": 0
    }

def end_encounter(state:Dict):
    enc=state.get("encounter")
    if not enc: return
    # Award XP equally to living party (very simple): 50 XP per monster defeated
    defeated = [c for c in enc["combatants"] if not c["is_player"] and (c["dead"] or c["current_hp"]<=0)]
    xp = 50*len(defeated)
    state["encounter"]["xp_reward"]=xp
    living_players = [name for name,ch in state["characters"].items() if ch.get("current_hp",1)>0]
    if living_players:
        share = xp // len(living_players)
        for n in living_players:
            state["characters"][n]["experience"] = int(state["characters"][n].get("experience",0))+share
    state["encounter"]["active"]=False

def handle_ko_or_death(cbt:Dict, logs:List[str]):
    if cbt["current_hp"]>0: return
    # Drop to 0 and start death saves (PC) or dead (monster)
    if cbt["is_player"]:
        cbt["current_hp"]=0
        logs.append(f"{cbt['name']} falls to 0 HP and begins making death saving throws.")
    else:
        cbt["dead"]=True
        logs.append(f"{cbt['name']} is slain.")

def perform_death_save(cbt:Dict, logs:List[str]):
    if cbt["current_hp"]>0 or not cbt["is_player"] or cbt["dead"]: return
    roll_ = random.randint(1,20)
    if roll_==1:
        cbt["death_saves"]["fail"]+=2; res="critical fail (2 fails)"
    elif roll_==20:
        cbt["current_hp"]=1; cbt["death_saves"]={"success":0,"fail":0}; res="critical success—back to 1 HP!"
    elif roll_>=10:
        cbt["death_saves"]["success"]+=1; res="success"
    else:
        cbt["death_saves"]["fail"]+=1; res="fail"
    logs.append(f"{cbt['name']} makes a death save: {roll_} → {res}.")
    if cbt["death_saves"]["success"]>=3:
        logs.append(f"{cbt['name']} stabilizes at 0 HP.")
    if cbt["death_saves"]["fail"]>=3:
        cbt["dead"]=True
        logs.append(f"{cbt['name']} dies.")

# =================== Streamlit session state ===================

def init_state():
    for k,v in [
        ("history",[]), ("characters",{}), ("current_player",None),
        ("page","SETUP"), ("adventure_started",False),
        ("custom_setting_description",""), ("setup_setting","Classic Fantasy"),
        ("setup_genre","High Magic Quest"), ("setup_difficulty","Normal (Balanced)"),
        ("use_ai_narration", USE_AI_NARRATION_DEFAULT and (client is not None)),
        ("system_instruction", SYSTEM_INSTRUCTION),
        ("encounter", None), ("_scroll_to_top", False)
    ]:
        st.session_state.setdefault(k,v)
init_state()

# =================== Character creation (local) ===================

SETTINGS_OPTIONS = {
    "Classic Fantasy": ["High Magic Quest","Gritty Dungeon Crawl","Political Intrigue"],
    "Post-Apocalypse": ["Mutant Survival","Cybernetic Wasteland","Resource Scarcity"],
    "Cyberpunk": ["Corporate Espionage","Street Gang Warfare","AI Revolution"],
}

CLASS_OPTIONS = {
    "Classic Fantasy": ["Fighter","Wizard","Rogue","Cleric","Barbarian"],
    "Post-Apocalypse": ["Scavenger","Mutant","Tech Specialist","Warlord","Drifter"],
    "Cyberpunk": ["Street Samurai","Netrunner","Corpo","Techie","Gang Enforcer"],
}

RACE_OPTIONS = {
    "Classic Fantasy": ["Human","Elf","Dwarf","Halfling","Orc","Tiefling"],
    "Post-Apocalypse": ["Human","Mutant","Android","Cyborg","Beastkin"],
    "Cyberpunk": ["Human","Cyborg","Augmented","Synth","Clone"],
}
RACE_MODS = {
    "Human":{}, "Elf":{"dex_mod":1,"int_mod":1,"con_mod":-1}, "Dwarf":{"con_mod":2,"cha_mod":-1},
    "Halfling":{"dex_mod":1,"str_mod":-1}, "Orc":{"str_mod":2,"int_mod":-1,"cha_mod":-1},
    "Tiefling":{"cha_mod":1,"int_mod":1,"wis_mod":-1},
    "Mutant":{"str_mod":1,"con_mod":1,"cha_mod":-1}, "Android":{"int_mod":2,"wis_mod":-1},
    "Cyborg":{"str_mod":1,"con_mod":1,"dex_mod":-1}, "Beastkin":{"dex_mod":1,"wis_mod":1,"int_mod":-1},
    "Augmented":{"dex_mod":1,"int_mod":1,"wis_mod":-1}, "Synth":{"int_mod":2,"cha_mod":-1}, "Clone":{"wis_mod":1,"cha_mod":-1},
}

def create_character(name:str, race:str, role:str, desc:str)->Dict:
    # Base modifiers modest spread
    mods = {"str_mod":0,"dex_mod":0,"con_mod":0,"int_mod":0,"wis_mod":0,"cha_mod":0}
    # Nudge by class
    if "Fighter" in role or "Barbarian" in role: mods["str_mod"]=2
    if "Rogue" in role: mods["dex_mod"]=2
    if "Wizard" in role: mods["int_mod"]=2
    if "Cleric" in role: mods["wis_mod"]=2
    # Apply race
    for k,delta in RACE_MODS.get(race,{}).items(): mods[k]+=delta
    # Clamp between -1 and +3 (as your original)
    for k in mods: mods[k]=max(-1, min(3, mods[k]))
    base_inv = ["dagger","leather armor","shield","longsword","shortbow","20 arrows","backpack","boots","ring","amulet","helm"]
    inv = ["longsword","leather armor","shield","boots","ring","amulet","helm"] if role in ("Fighter","Cleric","Barbarian") else \
          ["rapier","leather armor","dagger","boots","ring","amulet","helm"]
    char = {
        "name": name, "race": race, "race_class": role, "description": desc,
        **mods,
        "current_hp": 20, "max_hp": 20, "morale_sanity": 100,
        "inventory": inv, "experience": 0, "level": 1, "equipped": {}
    }
    ensure_equipped(char)
    # auto-equip armor, main weapon, shield
    if "leather armor" in inv: equip(char,"body","leather armor")
    weapon = "longsword" if "longsword" in inv else "rapier" if "rapier" in inv else inv[0]
    equip(char,"right_arm",weapon)
    if "shield" in inv: equip(char,"left_arm","shield")
    if "boots" in inv: equip(char,"feet","boots")
    if "helm" in inv: equip(char,"head","helm")
    if "ring" in inv: equip(char,"right_hand","ring")
    if "amulet" in inv: equip(char,"neck","amulet")
    # spell setup for casters
    cls=canonical_class(role)
    if cls in CLASS_SPELLS:
        ensure_spell_fields(char)
    return char

# =================== UI: Setup ===================
st.title("🧙 RPG Storyteller DM (SRD-style, playable)")

if st.session_state["page"]=="SETUP":
    st.header("1) Campaign Setup")
    c1,c2 = st.columns([1,2])
    with c1:
        st.selectbox("Setting", list(SETTINGS_OPTIONS.keys()), key="setup_setting")
        st.selectbox("Genre", SETTINGS_OPTIONS[st.session_state["setup_setting"]], key="setup_genre")
        st.selectbox("Difficulty", ["Easy (Narrative Focus)","Normal (Balanced)","Hard (Lethal)"], key="setup_difficulty")
        st.toggle("Optional: AI narration", key="use_ai_narration", value=st.session_state["use_ai_narration"] and (client is not None), help="Flavor text only. Mechanics are local.")
    with c2:
        st.text_area("World details (optional)", key="custom_setting_description", height=120,
                     placeholder="City under a toxic dome; air filters are currency...")

    st.markdown("---")
    st.header("2) Create Your Party")
    cc1, cc2 = st.columns([1,2])
    with cc1:
        role_list = CLASS_OPTIONS[st.session_state["setup_setting"]]
        role = st.selectbox("Class/Role", role_list, key="setup_role")
        name = st.text_input("Character Name", key="setup_name")
        race = st.selectbox("Race", RACE_OPTIONS[st.session_state["setup_setting"]], key="setup_race")
        if st.button("Add Character"):
            if not name.strip():
                st.error("Please provide a character name.")
            elif name in st.session_state["characters"]:
                st.error("Name already used.")
            else:
                ch = create_character(name, race, role, st.session_state.get("setup_desc",""))
                st.session_state["characters"][name]=ch
                if not st.session_state["current_player"]:
                    st.session_state["current_player"]=name
                st.success(f"Added {name} ({race} {role}).")
                st.session_state["setup_name"]=""
    with cc2:
        st.text_area("Character Description (optional)", key="setup_desc", height=120)
        if st.session_state["characters"]:
            st.markdown("**Party:** " + ", ".join(st.session_state["characters"].keys()))
        else:
            st.info("No characters yet.")

    st.markdown("---")
    st.header("3) Start Game")
    if st.session_state["characters"]:
        if st.button("🚀 Begin Adventure"):
            st.session_state["adventure_started"]=True
            st.session_state["page"]="GAME"
            st.session_state["_scroll_to_top"]=True
            _scroll_to_top()
            st.rerun()
    else:
        st.warning("Create at least one character.")

# =================== UI: Game ===================
if st.session_state["page"]=="GAME":
    if st.session_state.get("_scroll_to_top"):
        _scroll_to_top()
        st.session_state["_scroll_to_top"]=False

    # Sidebar: Active Player + Controls
    with st.sidebar:
        with st.expander("Active Player", expanded=True):
            if st.session_state["characters"]:
                options=list(st.session_state["characters"].keys())
                idx = options.index(st.session_state["current_player"]) if st.session_state["current_player"] in options else 0
                def on_change_player():
                    st.session_state["current_player"]=st.session_state["player_sel"]
                    st.session_state["_scroll_to_top"]=True
                    st.rerun()
                st.selectbox("Current Turn", options, index=idx, key="player_sel", on_change=on_change_player)
                ch=st.session_state["characters"][st.session_state["current_player"]]
                ac, ac_src = ac_calc(ch)
                ch["level"]=level_for_xp(int(ch["experience"]))
                pb = prof_bonus_for_xp(int(ch["experience"]))
                st.markdown(f"**{ch['name']}** — {ch['race']} {ch['race_class']}")
                st.markdown(f"**Level:** {ch['level']} | **XP:** {ch['experience']} | **Proficiency:** +{pb}")
                st.markdown(f"**HP:** {ch['current_hp']}/{ch.get('max_hp', ch['current_hp'])}")
                st.markdown(f"**AC:** {ac}  \n<small>({ac_src})</small>", unsafe_allow_html=True)
                st.markdown("**Ability Modifiers**")
                c1,c2,c3=st.columns(3)
                with c1: st.markdown(f"STR {ch['str_mod']}  \nDEX {ch['dex_mod']}")
                with c2: st.markdown(f"CON {ch['con_mod']}  \nINT {ch['int_mod']}")
                with c3: st.markdown(f"WIS {ch['wis_mod']}  \nCHA {ch['cha_mod']}")
                st.markdown("---")
                st.markdown("**Inventory & Equipment**")
                # Inventory equip controls
                for i, itm in enumerate(ch["inventory"]):
                    cA,cB,cC=st.columns([4,3,2])
                    with cA: st.markdown(f"- {itm}")
                    with cB:
                        slot = st.selectbox("Slot", [SLOT_LABEL[s] for s in SLOTS], key=f"invslot_{i}")
                    with cC:
                        slot_key = {v:k for k,v in SLOT_LABEL.items()}[slot]
                        if st.button("Equip", key=f"equip_{i}"):
                            equip(ch, slot_key, itm)
                            st.session_state["_scroll_to_top"]=True
                            st.rerun()
                st.markdown("**Equipped:**")
                for s in SLOTS:
                    e=ch["equipped"].get(s)
                    label=SLOT_LABEL[s]
                    if e:
                        stats=e.get("stats",{})
                        if stats.get("type")=="weapon":
                            more=f"{stats.get('damage')} dmg; {'finesse ' if 'finesse' in (stats.get('properties') or []) else ''}{'(ranged)' if stats.get('ranged') else ''}"
                        elif stats.get("type")=="shield":
                            more=f"+{stats.get('ac_bonus',0)} AC shield"
                        elif stats.get("type")=="armor":
                            a=stats["armor"]; cap=a["dex_cap"]; dex=f"+DEX" if cap is None else (f"+DEX (max {cap})" if cap>0 else "")
                            more=f"{a['category']} AC {a['base']} {dex}"
                        else:
                            more=", ".join((stats.get("properties") or [])) or "—"
                        st.markdown(f"- **{label}**: {e['item']} — {more}")
                    else:
                        st.markdown(f"- **{label}**: —")

                # Spells (if caster)
                cls=canonical_class(ch.get("race_class"))
                if cls in CLASS_SPELLS:
                    ensure_spell_fields(ch)
                    st.markdown("---")
                    st.subheader("Spells (Level 1)")
                    slots=ch["spell_slots"]["1"]
                    st.markdown(f"**Slots:** {slots['current']}/{slots['max']}  \n**Prepared:** {', '.join(ch['spells_prepared']) or '—'}")
                    with st.expander("Manage Known & Prepared", expanded=False):
                        avail=class_spell_list(cls,1)
                        known = st.multiselect("Known Spells", options=avail, default=[s for s in ch["spells_known"] if s in avail], key="known_list")
                        limit = 1 + max(0, int(ch.get(CASTING_MOD.get(cls,"int_mod"),0)))
                        prepared = st.multiselect(f"Prepared (max {limit})", options=known, default=[s for s in ch["spells_prepared"] if s in known][:limit], key="prep_list")
                        if st.button("Save Spells"):
                            ch["spells_known"]=known
                            ch["spells_prepared"]=prepared[:limit]
                            st.success("Spells updated.")

        st.header("Game Controls")
        # Encounter controls
        with st.expander("Encounter Manager", expanded=True):
            enc=st.session_state.get("encounter")
            if not enc or not enc.get("active"):
                if st.button("Start Encounter"):
                    begin_encounter(st.session_state)
                    st.success("Encounter started. Add monsters below and roll initiative.")
                    st.session_state["_scroll_to_top"]=True; st.rerun()
            else:
                st.info(f"Round {enc['round']} | Turn: {enc['turn_index']+1}/{len(enc['combatants'])}")

            if st.session_state.get("encounter"):
                enc=st.session_state["encounter"]
                if enc.get("active"):
                    # Add monsters
                    mC1,mC2 = st.columns([2,1])
                    with mC1:
                        mtype = st.selectbox("Add Monster (template)", list(MONSTERS.keys()), key="mtype")
                        mname = st.text_input("Monster Name", value=f"{mtype} #{random.randint(1,99)}", key="mname")
                    with mC2:
                        if st.button("Add"):
                            enc["combatants"].append(new_monster(mname or mtype, mtype))
                            st.success(f"Added {mname or mtype}.")
                    st.markdown("**Combatants:**")
                    for cbt in enc["combatants"]:
                        st.markdown(f"- {cbt['name']} — AC {cbt['ac']} | HP {cbt['current_hp']}/{cbt['max_hp']} {'(DEAD)' if cbt.get('dead') else ''}")

                    st.markdown("---")
                    if not enc["initiative"]:
                        if st.button("Roll Initiative For All"):
                            init = []
                            for c in enc["combatants"]:
                                init.append((c["name"], roll_initiative(c)))
                            init.sort(key=lambda x: x[1], reverse=True)
                            enc["initiative"]=init
                            # reorder combatants by initiative
                            order = [n for n,_ in init]
                            enc["combatants"].sort(key=lambda c: order.index(c["name"]))
                            st.success("Initiative set.")
                            st.rerun()
                    else:
                        st.markdown("**Initiative:** " + " → ".join([f"{n}({i})" for n,i in enc["initiative"]]))
                        cA,cB,cC,cD = st.columns(4)
                        if cA.button("Next Turn"):
                            enc["turn_index"] = (enc["turn_index"]+1) % len(enc["combatants"])
                            if enc["turn_index"]==0: enc["round"]+=1
                            # auto death saves at start of turn if downed PC
                            acting = enc["combatants"][enc["turn_index"]]
                            if acting["is_player"] and acting["current_hp"]==0 and not acting["dead"]:
                                perform_death_save(acting, enc["log"])
                            st.rerun()
                        if cB.button("End Encounter"):
                            end_encounter(st.session_state)
                            xp = st.session_state["encounter"]["xp_reward"]
                            st.success(f"Encounter ended. Party awarded {xp} XP (split).")
                            st.rerun()
                        if cC.button("Short Rest"):
                            for c in enc["combatants"]:
                                if c["is_player"] and not c.get("dead"):
                                    cobj=st.session_state["characters"][c["name"]]
                                    heal = max(1, 2+int(cobj.get("con_mod",0)))
                                    cobj["current_hp"] = min(cobj.get("max_hp",20), cobj["current_hp"]+heal)
                                    c["current_hp"]=cobj["current_hp"]
                            st.info("Short Rest: each PC recovers a small amount of HP.")
                        if cD.button("Long Rest"):
                            for c in enc["combatants"]:
                                if c["is_player"] and not c.get("dead"):
                                    cobj=st.session_state["characters"][c["name"]]
                                    cobj["current_hp"]=cobj.get("max_hp",20)
                                    # restore slots
                                    cls=canonical_class(cobj.get("race_class"))
                                    if cls in CLASS_SLOTS:
                                        m=CLASS_SLOTS[cls]["1"]
                                        cobj.setdefault("spell_slots",{}); cobj["spell_slots"]["1"]={"max":m,"current":m}
                                    c["current_hp"]=cobj["current_hp"]
                            enc["bless"]=set()
                            st.info("Long Rest: PCs fully heal and recover slots.")

        st.markdown("---")
        st.subheader("Save / Load")
        if st.button("💾 Save Game"):
            payload = {
                "characters": st.session_state["characters"],
                "current_player": st.session_state["current_player"],
                "setting": st.session_state["setup_setting"],
                "genre": st.session_state["setup_genre"],
                "difficulty": st.session_state["setup_difficulty"],
                "use_ai_narration": st.session_state["use_ai_narration"]
            }
            st.download_button("Download Save JSON", data=json.dumps(payload, indent=2),
                               file_name="srd_rpg_save.json", mime="application/json")
        up = st.file_uploader("Load Save", type="json")
        if up and st.button("Load Now"):
            try:
                data=json.loads(up.read())
                st.session_state["characters"]=data["characters"]
                st.session_state["current_player"]=data["current_player"]
                st.session_state["setup_setting"]=data.get("setting","Classic Fantasy")
                st.session_state["setup_genre"]=data.get("genre","High Magic Quest")
                st.session_state["setup_difficulty"]=data.get("difficulty","Normal (Balanced)")
                st.session_state["use_ai_narration"]=data.get("use_ai_narration",False) and (client is not None)
                st.success("Loaded.")
                st.rerun()
            except Exception as e:
                st.error(f"Load error: {e}")

        st.markdown('<small class="srd-note">Includes material compatible with the D&D 5e SRD (CC-BY-4.0). This app uses original wording for rules and brief functional spell summaries.</small>', unsafe_allow_html=True)

    # ======== Main column: Story Log + Action Console ========
    col_main = st.container()
    with col_main:
        st.header("The Story Log")
        # Show minimal story; we log mechanics below, and optional narration
        if "history" not in st.session_state: st.session_state["history"]=[]
        for msg in st.session_state["history"][-100:]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # ---- Action Console ----
        enc=st.session_state.get("encounter")
        ch=st.session_state["characters"][st.session_state["current_player"]]

        st.subheader("Action Console")
        # If in encounter, show combat actions
        if enc and enc.get("active") and enc.get("initiative"):
            acting = enc["combatants"][enc["turn_index"]]
            st.caption(f"Acting: {acting['name']} (Round {enc['round']})")

            # Only allow PC actions on their turn
            if acting["is_player"] and acting["name"]==ch["name"] and not acting.get("dead"):
                cA,cB = st.columns(2)
                with cA:
                    st.markdown("**Attack (Weapon)**")
                    # Choose equipped weapon in arms
                    arms=[]
                    for s in ("right_arm","left_arm"):
                        e=ch["equipped"].get(s)
                        if e and e.get("stats",{}).get("type")=="weapon":
                            if e not in arms: arms.append(e)
                    wep = st.selectbox("Weapon", [e["item"] for e in arms] or ["—"], key="atk_wep")
                    targets=[c["name"] for c in enc["combatants"] if not c["is_player"] and not c.get("dead") and c["current_hp"]>0]
                    tgt = st.selectbox("Target", targets or ["—"], key="atk_tgt")
                    if st.button("Attack!"):
                        if wep=="—" or tgt=="—":
                            st.warning("Pick a weapon and a target.")
                        else:
                            wstats=item_stats(wep) or {}
                            bonus, abil = dm_attack_bonus(ch, wstats)
                            bless_bonus = roll("1d4") if ch["name"] in enc.get("bless", set()) else 0
                            d20 = random.randint(1,20)
                            total = d20 + bonus + bless_bonus
                            target = next(x for x in enc["combatants"] if x["name"]==tgt)
                            crit = (d20==20)
                            hit = (total >= target["ac"]) or crit
                            lines=[f"{ch['name']} attacks {tgt} with {wep}: d20 {d20} + bonus {bonus}{' + bless '+str(bless_bonus) if bless_bonus else ''} = {total} vs AC {target['ac']} — {'HIT' if hit else 'MISS'}."]
                            if hit:
                                base = dm_damage_roll(wstats, int(ch.get(abil,0)))
                                dmg = base*2 if crit else base
                                target["current_hp"]-=dmg
                                lines.append(f"Damage: {dmg}.")
                                if target["current_hp"]<=0: handle_ko_or_death(target, lines)
                            enc["log"].extend(lines)
                            st.session_state["history"].append({"role":"assistant","content":"\n".join(lines)})
                            # optional narration
                            if st.session_state["use_ai_narration"]:
                                out = ai_narrate(st.session_state["history"][-5:], st.session_state["system_instruction"])
                                if out: st.session_state["history"].append({"role":"assistant","content": out})
                            st.session_state["_scroll_to_top"]=True; st.rerun()

                with cB:
                    # Spells
                    cls=canonical_class(ch.get("race_class"))
                    if cls in CLASS_SPELLS:
                        st.markdown("**Cast Spell (Lv1)**")
                        ensure_spell_fields(ch)
                        prepared = ch["spells_prepared"]
                        sname = st.selectbox("Spell", prepared or ["—"], key="cast_spell")
                        all_targets = [c["name"] for c in enc["combatants"] if c["name"]!=ch["name"] and not c.get("dead")]
                        s_tgt = st.selectbox("Target (if needed)", all_targets or ["—"], key="cast_target")
                        if st.button("Cast"):
                            if sname=="—":
                                st.warning("Pick a spell.")
                            else:
                                logs=do_spell_effect(st.session_state, ch, sname, s_tgt if s_tgt!="—" else "")
                                enc["log"].extend(logs)
                                st.session_state["history"].append({"role":"assistant","content":"\n".join(logs)})
                                if st.session_state["use_ai_narration"]:
                                    out = ai_narrate(st.session_state["history"][-5:], st.session_state["system_instruction"])
                                    if out: st.session_state["history"].append({"role":"assistant","content": out})
                                st.session_state["_scroll_to_top"]=True; st.rerun()

                st.markdown('<hr class="slim">', unsafe_allow_html=True)
                cX,cY,cZ = st.columns(3)
                with cX:
                    if st.button("Dodge / Disengage / Dash"):
                        st.session_state["history"].append({"role":"assistant","content": f"{ch['name']} takes a defensive or tactical action, repositioning."})
                        if st.session_state["use_ai_narration"]:
                            out = ai_narrate(st.session_state["history"][-5:], st.session_state["system_instruction"])
                            if out: st.session_state["history"].append({"role":"assistant","content": out})
                        st.session_state["_scroll_to_top"]=True; st.rerun()
                with cY:
                    heal_amt = st.number_input("Use Item / Heal HP", min_value=0, max_value=50, value=0, step=1)
                    if st.button("Apply Self-Heal"):
                        ch["current_hp"]=min(ch.get("max_hp",20), ch["current_hp"]+int(heal_amt))
                        st.session_state["history"].append({"role":"assistant","content": f"{ch['name']} uses an item and recovers {heal_amt} HP."})
                        st.session_state["_scroll_to_top"]=True; st.rerun()
                with cZ:
                    if st.button("End My Turn"):
                        # advance encounter turn
                        enc["turn_index"]=(enc["turn_index"]+1)%len(enc["combatants"])
                        if enc["turn_index"]==0: enc["round"]+=1
                        # death save if next actor is a downed PC
                        nxt=enc["combatants"][enc["turn_index"]]
                        if nxt["is_player"] and nxt["current_hp"]==0 and not nxt.get("dead"):
                            perform_death_save(nxt, enc["log"])
                        st.session_state["_scroll_to_top"]=True; st.rerun()
            else:
                st.info("Not your turn or you are down/dead.")
        else:
            # Freeform exploration / narration
            prompt = st.chat_input("What do you do?")
            with st.container():
                st.markdown('<div class="continue-bar"></div>', unsafe_allow_html=True)
                cont = st.button("▶ Continue / Next scene")
            if (prompt is not None and prompt.strip()!="") or cont:
                content = prompt.strip() if prompt and prompt.strip() else "(The party advances; describe the next meaningful beat.)"
                st.session_state["history"].append({"role":"user","content":f"({st.session_state['current_player']}): {content}"})
                # Minimal narrative or AI
                if st.session_state["use_ai_narration"]:
                    out=ai_narrate(st.session_state["history"][-8:], st.session_state["system_instruction"])
                    st.session_state["history"].append({"role":"assistant","content": out or "(The world waits...)"})
                else:
                    st.session_state["history"].append({"role":"assistant","content":"The path narrows; torchlight flickers. What do you do next?"})
                st.session_state["_scroll_to_top"]=True
                st.rerun()
