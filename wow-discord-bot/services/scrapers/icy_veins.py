import httpx
from bs4 import BeautifulSoup


HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

BASE_URL = "https://www.icy-veins.com/wow"

# Maps (spec, class) → Icy Veins guide URL slug
GUIDE_SLUGS: dict[tuple[str, str], str] = {
    ("Blood", "Death Knight"): "blood-death-knight-pve-tank-guide",
    ("Frost", "Death Knight"): "frost-death-knight-pve-dps-guide",
    ("Unholy", "Death Knight"): "unholy-death-knight-pve-dps-guide",
    ("Havoc", "Demon Hunter"): "havoc-demon-hunter-pve-dps-guide",
    ("Vengeance", "Demon Hunter"): "vengeance-demon-hunter-pve-tank-guide",
    ("Balance", "Druid"): "balance-druid-pve-dps-guide",
    ("Feral", "Druid"): "feral-druid-pve-dps-guide",
    ("Guardian", "Druid"): "guardian-druid-pve-tank-guide",
    ("Restoration", "Druid"): "restoration-druid-pve-healer-guide",
    ("Augmentation", "Evoker"): "augmentation-evoker-pve-dps-guide",
    ("Devastation", "Evoker"): "devastation-evoker-pve-dps-guide",
    ("Preservation", "Evoker"): "preservation-evoker-pve-healer-guide",
    ("Beast Mastery", "Hunter"): "beast-mastery-hunter-pve-dps-guide",
    ("Marksmanship", "Hunter"): "marksmanship-hunter-pve-dps-guide",
    ("Survival", "Hunter"): "survival-hunter-pve-dps-guide",
    ("Arcane", "Mage"): "arcane-mage-pve-dps-guide",
    ("Fire", "Mage"): "fire-mage-pve-dps-guide",
    ("Frost", "Mage"): "frost-mage-pve-dps-guide",
    ("Brewmaster", "Monk"): "brewmaster-monk-pve-tank-guide",
    ("Mistweaver", "Monk"): "mistweaver-monk-pve-healer-guide",
    ("Windwalker", "Monk"): "windwalker-monk-pve-dps-guide",
    ("Holy", "Paladin"): "holy-paladin-pve-healer-guide",
    ("Protection", "Paladin"): "protection-paladin-pve-tank-guide",
    ("Retribution", "Paladin"): "retribution-paladin-pve-dps-guide",
    ("Discipline", "Priest"): "discipline-priest-pve-healer-guide",
    ("Holy", "Priest"): "holy-priest-pve-healer-guide",
    ("Shadow", "Priest"): "shadow-priest-pve-dps-guide",
    ("Assassination", "Rogue"): "assassination-rogue-pve-dps-guide",
    ("Outlaw", "Rogue"): "outlaw-rogue-pve-dps-guide",
    ("Subtlety", "Rogue"): "subtlety-rogue-pve-dps-guide",
    ("Elemental", "Shaman"): "elemental-shaman-pve-dps-guide",
    ("Enhancement", "Shaman"): "enhancement-shaman-pve-dps-guide",
    ("Restoration", "Shaman"): "restoration-shaman-pve-healer-guide",
    ("Affliction", "Warlock"): "affliction-warlock-pve-dps-guide",
    ("Demonology", "Warlock"): "demonology-warlock-pve-dps-guide",
    ("Destruction", "Warlock"): "destruction-warlock-pve-dps-guide",
    ("Arms", "Warrior"): "arms-warrior-pve-dps-guide",
    ("Fury", "Warrior"): "fury-warrior-pve-dps-guide",
    ("Protection", "Warrior"): "protection-warrior-pve-tank-guide",
}


async def fetch_stat_priority(spec: str, wow_class: str) -> list[str]:
    """
    Fetch the stat priority list from an Icy Veins stat priority page.
    Returns a list like ['Intellect', 'Mastery', 'Critical Strike', 'Haste', 'Versatility'].
    """
    slug = GUIDE_SLUGS.get((spec, wow_class))
    if not slug:
        slug = f"{spec.lower().replace(' ', '-')}-{wow_class.lower().replace(' ', '-')}-pve-dps-guide"

    stat_slug = slug.replace("-guide", "-stat-priority")
    url = f"{BASE_URL}/{stat_slug}"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # The stats are in an <ol> inside the main page content
    ol = soup.select_one("div.page_content ol")
    if ol:
        return [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]

    # Fallback: first <ol> anywhere on the page
    ol = soup.find("ol")
    if ol:
        return [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]

    return []


async def fetch_class_updates(spec: str, wow_class: str) -> str:
    """
    Fetch the 'Recent Updates' or changelog section from an Icy Veins
    class guide for the given spec/class combination.
    """
    slug = GUIDE_SLUGS.get((spec, wow_class))
    if not slug:
        # Fallback: construct a guess
        slug = f"{spec.lower().replace(' ', '-')}-{wow_class.lower().replace(' ', '-')}-guide"

    url = f"https://www.icy-veins.com/wow/{slug}"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Icy Veins structure: heading is inside div.heading_container,
    # content is in the next sibling divs after that container
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True).lower()
        if any(kw in text for kw in ("recent update", "changelog", "patch", "change")):
            container = heading.find_parent("div", class_="heading_container") or heading
            content_parts = []
            for sibling in container.find_next_siblings():
                # Stop at next heading container
                if sibling.find("div", class_="heading_container"):
                    break
                if sibling.find(["h2", "h3"]):
                    break
                t = sibling.get_text(separator=" ", strip=True)
                if t:
                    content_parts.append(t)
                if len(" ".join(content_parts)) > 2000:
                    break
            if content_parts:
                return "\n".join(content_parts)[:2000]

    # Fallback: intro paragraph
    intro = soup.select_one(".introduction, .guide-intro, main p")
    if intro:
        return intro.get_text(separator="\n", strip=True)[:1000]
    return ""
