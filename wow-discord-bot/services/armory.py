from dataclasses import dataclass
from typing import Optional

from services import blizzard_api


@dataclass
class CharacterProfile:
    name: str
    realm: str
    wow_class: str
    spec: str
    role: str           # inferred from spec
    faction: str
    average_ilvl: int
    equipped_ilvl: int


# Maps spec name to role — covers all current retail specs
SPEC_TO_ROLE: dict[str, str] = {
    # Death Knight
    "Blood": "tank", "Frost": "dps", "Unholy": "dps",
    # Demon Hunter
    "Havoc": "dps", "Vengeance": "tank",
    # Druid
    "Balance": "dps", "Feral": "dps", "Guardian": "tank", "Restoration": "healer",
    # Evoker
    "Augmentation": "dps", "Devastation": "dps", "Preservation": "healer",
    # Hunter
    "Beast Mastery": "dps", "Marksmanship": "dps", "Survival": "dps",
    # Mage
    "Arcane": "dps", # "Frost" already above, "Fire" below
    "Fire": "dps",
    # Monk
    "Brewmaster": "tank", "Mistweaver": "healer", "Windwalker": "dps",
    # Paladin
    "Holy": "healer", "Protection": "tank", "Retribution": "dps",
    # Priest
    "Discipline": "healer", "Shadow": "dps",
    # Rogue
    "Assassination": "dps", "Outlaw": "dps", "Subtlety": "dps",
    # Shaman
    "Elemental": "dps", "Enhancement": "dps",
    # Warlock
    "Affliction": "dps", "Demonology": "dps", "Destruction": "dps",
    # Warrior
    "Arms": "dps", "Fury": "dps",
}


async def lookup_character(realm: str, name: str) -> Optional[CharacterProfile]:
    """
    Fetch character data from WoW Armory (via Battle.net API) and
    return a structured CharacterProfile, or None if not found.
    """
    data = await blizzard_api.get_character(realm, name)
    if data is None:
        return None

    char_class = data.get("character_class", {}).get("name", "Unknown")
    active_spec_data = data.get("active_spec", {})
    spec_name = active_spec_data.get("name", "Unknown")

    role = SPEC_TO_ROLE.get(spec_name, "dps")

    faction = data.get("faction", {}).get("name", "Unknown")
    avg_ilvl = data.get("average_item_level", 0)
    equipped_ilvl = data.get("equipped_item_level", 0)

    return CharacterProfile(
        name=data.get("name", name),
        realm=data.get("realm", {}).get("name", realm),
        wow_class=char_class,
        spec=spec_name,
        role=role,
        faction=faction,
        average_ilvl=avg_ilvl,
        equipped_ilvl=equipped_ilvl,
    )
