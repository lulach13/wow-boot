"""Tests for the Armory -> CharacterProfile mapping.

We never hit the live Battle.net API here; blizzard_api.get_character is
patched out. What we actually care about is that the raw JSON blob Blizzard
returns gets mapped into a CharacterProfile correctly, including the spec->role
inference and the fallbacks for missing fields.
"""
import pytest

from services import armory


def _fake_character(**overrides):
    data = {
        "name": "Thrall",
        "realm": {"name": "Silvermoon"},
        "character_class": {"name": "Shaman"},
        "active_spec": {"name": "Enhancement"},
        "faction": {"name": "Horde"},
        "average_item_level": 486,
        "equipped_item_level": 480,
    }
    data.update(overrides)
    return data


def _patch_api(monkeypatch, return_value):
    async def fake_get_character(realm, name):
        return return_value
    monkeypatch.setattr(armory.blizzard_api, "get_character", fake_get_character)


async def test_maps_full_profile(monkeypatch):
    _patch_api(monkeypatch, _fake_character())

    profile = await armory.lookup_character("Silvermoon", "Thrall")

    assert profile is not None
    assert profile.name == "Thrall"
    assert profile.realm == "Silvermoon"
    assert profile.wow_class == "Shaman"
    assert profile.spec == "Enhancement"
    assert profile.role == "dps"
    assert profile.faction == "Horde"
    assert profile.average_ilvl == 486
    assert profile.equipped_ilvl == 480


async def test_tank_spec_infers_tank_role(monkeypatch):
    _patch_api(monkeypatch, _fake_character(
        character_class={"name": "Death Knight"},
        active_spec={"name": "Blood"},
    ))

    profile = await armory.lookup_character("Silvermoon", "Bloodguy")

    assert profile.role == "tank"


async def test_missing_character_returns_none(monkeypatch):
    # 404 from the API surfaces as None from get_character
    _patch_api(monkeypatch, None)

    profile = await armory.lookup_character("Silvermoon", "Ghost")

    assert profile is None


async def test_unknown_spec_falls_back_to_dps(monkeypatch):
    # A spec we don't have in the SPEC_TO_ROLE table shouldn't blow up — it
    # should quietly default to dps rather than raising a KeyError.
    _patch_api(monkeypatch, _fake_character(active_spec={"name": "Tinkerer"}))

    profile = await armory.lookup_character("Silvermoon", "Gnomeguy")

    assert profile.role == "dps"


async def test_partial_payload_uses_defaults(monkeypatch):
    # Blizzard occasionally returns a sparse profile (e.g. brand new or
    # transferred character). Missing keys should degrade to sane defaults,
    # not KeyErrors.
    _patch_api(monkeypatch, {"name": "Sparse"})

    profile = await armory.lookup_character("Silvermoon", "Sparse")

    assert profile.wow_class == "Unknown"
    assert profile.spec == "Unknown"
    assert profile.faction == "Unknown"
    assert profile.average_ilvl == 0
    assert profile.equipped_ilvl == 0
    # falls back to the name we passed in when the payload omits it
    assert profile.realm == "Silvermoon"
