import httpx
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

BASE_URL = "https://www.wowhead.com"

STAT_PRIORITY_KNOWN_STATS = {
    "intellect", "mastery", "critical strike", "haste",
    "versatility", "strength", "agility", "stamina",
    "speed", "leech", "avoidance",
}


def _to_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


async def fetch_stat_priority(spec: str, wow_class: str, role: str = "dps") -> list[dict]:
    """
    Fetch stat priority list(s) from the Wowhead class guide stat priority page.
    Returns a list of dicts: [{"label": "Frostfire Stat Priority", "stats": ["Intellect", ...]}, ...]
    Each dict represents one hero talent build found on the page.
    """
    class_slug = _to_slug(wow_class)
    spec_slug = _to_slug(spec)
    role_slug = role.lower()

    url = f"{BASE_URL}/guide/classes/{class_slug}/{spec_slug}/stat-priority-pve-{role_slug}"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for td in soup.find_all("td"):
        ol = td.find("ol")
        if not ol:
            continue

        stats = [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]
        if not stats:
            continue

        # Only keep lists that look like stat priority (contain known WoW stats)
        normalized = [s.lower() for s in stats]
        if not any(s in STAT_PRIORITY_KNOWN_STATS for s in normalized):
            continue

        # Extract the label from the bold tag before the ol. Wowhead sometimes
        # renders it as "] Frostfire Build" (leftover bracket from an icon span),
        # so strip a leading "]" before using it.
        label_tag = td.find("b")
        label = label_tag.get_text(strip=True).lstrip("]").strip() if label_tag else f"{spec} {wow_class} Stat Priority"

        results.append({"label": label, "stats": stats, "url": url})

    return results


async def fetch_patch_coverage(patch_title: str, patch_url: str) -> str:
    """
    Search Wowhead news for coverage of a specific patch and return
    the article text. Falls back to searching by patch title keywords.
    """
    # First try to find a Wowhead article about this patch
    search_query = patch_title.replace(" ", "+")
    search_url = f"https://www.wowhead.com/news?search={search_query}"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(search_url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the first relevant article link
    article_link = None
    for a in soup.select("a[href*='/news/']"):
        text = a.get_text(strip=True).lower()
        if any(kw in text for kw in ("patch", "hotfix", "update")):
            article_link = a.get("href")
            break

    if not article_link:
        return ""

    if not article_link.startswith("http"):
        article_link = f"https://www.wowhead.com{article_link}"

    return await _fetch_article_text(article_link)


async def _fetch_article_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.select_one(".news-content, .article-content, #content-text, main article")
    if content:
        return content.get_text(separator="\n", strip=True)[:4000]
    return ""
