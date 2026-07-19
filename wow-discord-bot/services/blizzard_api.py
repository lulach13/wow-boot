import time
import httpx
from dataclasses import dataclass
from typing import Optional

from config import settings

_token_cache: dict = {"access_token": None, "expires_at": 0}


async def _get_access_token(client: httpx.AsyncClient) -> str:
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    resp = await client.post(
        "https://oauth.battle.net/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.blizzard_client_id, settings.blizzard_client_secret),
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["access_token"]


async def get_character(realm: str, name: str) -> Optional[dict]:
    """Fetch character profile from Battle.net API."""
    realm_slug = realm.lower().replace(" ", "-").replace("'", "")
    name_lower = name.lower()
    region = settings.blizzard_region

    async with httpx.AsyncClient(timeout=15) as client:
        token = await _get_access_token(client)
        url = (
            f"https://{region}.api.blizzard.com/profile/wow/character"
            f"/{realm_slug}/{name_lower}"
        )
        resp = await client.get(
            url,
            params={
                "namespace": f"profile-{region}",
                "locale": "en_US",
                "access_token": token,
            },
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


@dataclass
class PatchNoteEntry:
    title: str
    url: str
    published: str


async def get_latest_patch_notes(count: int = 5) -> list[PatchNoteEntry]:
    """
    Scrape the Blizzard WoW news page for patch note / hotfix articles.
    Returns the most recent ones (up to `count`).
    """
    import re
    from bs4 import BeautifulSoup

    url = "https://worldofwarcraft.blizzard.com/en-us/news"
    keywords = ("patch notes", "hotfixes", "hotfix", "update notes")

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "WoWBot/1.0"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[PatchNoteEntry] = []

    for article in soup.select("article, .NewsBlog-item, .blog-item"):
        title_el = article.select_one("h2, h3, .blog-title, .NewsBlog-title")
        link_el = article.select_one("a[href]")
        date_el = article.select_one("time, .blog-date, .NewsBlog-date")

        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        if not any(kw in title.lower() for kw in keywords):
            continue

        href = link_el["href"]
        if not href.startswith("http"):
            href = f"https://worldofwarcraft.blizzard.com{href}"

        published = date_el.get("datetime", date_el.get_text(strip=True)) if date_el else ""
        results.append(PatchNoteEntry(title=title, url=href, published=published))

        if len(results) >= count:
            break

    return results


async def fetch_patch_note_content(url: str) -> str:
    """Fetch the full text of a patch note article."""
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "WoWBot/1.0"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    content_el = soup.select_one(".blog-content, .NewsBlog-content, article .detail-content, main")
    if content_el:
        return content_el.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)[:8000]
