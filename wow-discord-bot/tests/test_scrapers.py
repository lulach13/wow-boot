"""Scraper parsing tests driven off saved HTML fixtures.

These never touch the network. We swap httpx.AsyncClient for a fake that
replays a fixture file, so what's under test is purely the BeautifulSoup
parsing/filtering logic — which is the part that actually breaks when Icy
Veins or Wowhead change their markup.
"""
import pytest

from services.scrapers import icy_veins, wowhead
from tests.conftest import load_fixture


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    def __init__(self, text: str, status_code: int = 200):
        self._text = text
        self._status = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, params=None):
        return _FakeResponse(self._text, self._status)


def _fake_client_factory(text, status_code=200):
    def factory(*args, **kwargs):
        return _FakeClient(text, status_code)
    return factory


async def test_icy_veins_parses_ordered_stat_list(monkeypatch):
    html = load_fixture("icy_veins_stat_priority.html")
    monkeypatch.setattr(icy_veins.httpx, "AsyncClient", _fake_client_factory(html))

    stats = await icy_veins.fetch_stat_priority("Frost", "Mage")

    assert stats == ["Intellect", "Haste", "Mastery", "Critical Strike", "Versatility"]


async def test_icy_veins_returns_empty_on_http_error(monkeypatch):
    monkeypatch.setattr(
        icy_veins.httpx, "AsyncClient", _fake_client_factory("", status_code=503)
    )

    stats = await icy_veins.fetch_stat_priority("Frost", "Mage")

    assert stats == []


async def test_wowhead_extracts_each_build_and_strips_bracket(monkeypatch):
    html = load_fixture("wowhead_stat_priority.html")
    monkeypatch.setattr(wowhead.httpx, "AsyncClient", _fake_client_factory(html))

    builds = await wowhead.fetch_stat_priority("Frost", "Mage", role="dps")

    # Two real stat-priority builds; the table-of-contents <ol> is ignored.
    assert len(builds) == 2

    labels = [b["label"] for b in builds]
    assert "Frostfire Build" in labels  # leading "] " stripped
    assert "Spellslinger Build" in labels

    frostfire = next(b for b in builds if b["label"] == "Frostfire Build")
    assert frostfire["stats"][0] == "Intellect"
    assert "Critical Strike" in frostfire["stats"]


async def test_wowhead_ignores_non_stat_lists(monkeypatch):
    # Page with only a table-of-contents style list -> nothing stat-like to keep.
    html = """
    <table><tr><td><ol>
      <li>Introduction</li><li>Talents</li><li>Gear</li>
    </ol></td></tr></table>
    """
    monkeypatch.setattr(wowhead.httpx, "AsyncClient", _fake_client_factory(html))

    builds = await wowhead.fetch_stat_priority("Frost", "Mage", role="dps")

    assert builds == []
