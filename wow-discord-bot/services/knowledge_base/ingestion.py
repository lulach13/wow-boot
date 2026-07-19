import logging

import httpx
from bs4 import BeautifulSoup

from services.knowledge_base.embedder import chunk_text
from services.knowledge_base.vector_store import get_vector_store
from services.scrapers.icy_veins import BASE_URL as IV_BASE_URL, GUIDE_SLUGS, HEADERS as IV_HEADERS
from services.scrapers.wowhead import BASE_URL as WH_BASE_URL, HEADERS as WH_HEADERS

logger = logging.getLogger(__name__)


async def _fetch_page_text(url: str, headers: dict) -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Could not fetch {url}: {e}")
            return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove nav, header, footer, scripts, ads
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    content = soup.select_one("div.page_content, main, article, #content-text, #content")
    if content:
        return content.get_text(separator=" ", strip=True)
    return soup.get_text(separator=" ", strip=True)


async def ingest_icy_veins(class_name: str, spec: str) -> int:
    """Scrape Icy Veins guide pages for a spec and store chunks. Returns chunk count."""
    slug = GUIDE_SLUGS.get((spec, class_name))
    if not slug:
        slug = (
            f"{spec.lower().replace(' ', '-')}"
            f"-{class_name.lower().replace(' ', '-')}-pve-dps-guide"
        )

    base = slug.replace("-guide", "")
    topics = {
        "stat-priority": f"{IV_BASE_URL}/{base}-stat-priority",
        "talents": f"{IV_BASE_URL}/{base}-talents",
        "gear": f"{IV_BASE_URL}/{base}-gear-best-in-slot",
        "rotation": f"{IV_BASE_URL}/{base}-rotation-cooldowns",
    }

    store = get_vector_store()
    total = 0

    for topic, url in topics.items():
        text = await _fetch_page_text(url, IV_HEADERS)
        if not text:
            logger.info(f"[IV] No content: {spec} {class_name} / {topic}")
            continue

        chunks = chunk_text(text)
        docs = [
            {
                "text": chunk,
                "metadata": {
                    "source": "icy_veins",
                    "class": class_name,
                    "spec": spec,
                    "topic": topic,
                    "url": url,
                },
            }
            for chunk in chunks
        ]
        store.add_documents(docs)
        total += len(docs)
        logger.info(f"[IV] {spec} {class_name} / {topic}: {len(docs)} chunks")

    return total


async def ingest_wowhead(class_name: str, spec: str) -> int:
    """Scrape Wowhead guide pages for a spec and store chunks. Returns chunk count."""
    from bot.cogs.registration import get_role

    role = get_role(spec)
    class_slug = class_name.lower().replace(" ", "-")
    spec_slug = spec.lower().replace(" ", "-")

    topics = {
        "stat-priority": f"{WH_BASE_URL}/guide/classes/{class_slug}/{spec_slug}/stat-priority-pve-{role}",
        "talents": f"{WH_BASE_URL}/guide/classes/{class_slug}/{spec_slug}/talents-pve-{role}",
        "gear": f"{WH_BASE_URL}/guide/classes/{class_slug}/{spec_slug}/best-in-slot-pve-{role}",
        "rotation": f"{WH_BASE_URL}/guide/classes/{class_slug}/{spec_slug}/rotation-pve-{role}",
    }

    store = get_vector_store()
    total = 0

    for topic, url in topics.items():
        text = await _fetch_page_text(url, WH_HEADERS)
        if not text:
            logger.info(f"[WH] No content: {spec} {class_name} / {topic}")
            continue

        chunks = chunk_text(text)
        docs = [
            {
                "text": chunk,
                "metadata": {
                    "source": "wowhead",
                    "class": class_name,
                    "spec": spec,
                    "topic": topic,
                    "url": url,
                },
            }
            for chunk in chunks
        ]
        store.add_documents(docs)
        total += len(docs)
        logger.info(f"[WH] {spec} {class_name} / {topic}: {len(docs)} chunks")

    return total


async def ingest_all_registered_specs() -> dict:
    """Query DB for distinct (class, spec) pairs and ingest both sources for each."""
    from db.database import get_session
    from db.models import User

    with get_session() as session:
        rows = session.query(User.wow_class, User.spec).distinct().all()
        specs = [(r.wow_class, r.spec) for r in rows if r.wow_class and r.spec]

    if not specs:
        logger.info("No registered specs to ingest.")
        return {"specs": 0, "chunks": 0}

    total_chunks = 0

    for class_name, spec in specs:
        logger.info(f"Ingesting {spec} {class_name}...")

        try:
            total_chunks += await ingest_icy_veins(class_name, spec)
        except Exception as e:
            logger.error(f"Icy Veins ingestion failed for {spec} {class_name}: {e}")

        try:
            total_chunks += await ingest_wowhead(class_name, spec)
        except Exception as e:
            logger.error(f"Wowhead ingestion failed for {spec} {class_name}: {e}")

    logger.info(f"Ingestion complete: {total_chunks} chunks across {len(specs)} spec(s).")
    return {"specs": len(specs), "chunks": total_chunks}
