import logging

from services.knowledge_base.vector_store import get_vector_store

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "icy_veins": "Icy Veins",
    "wowhead": "Wowhead",
}


def query_knowledge(
    class_name: str,
    spec: str,
    question: str,
    sources: list | None = None,
    n_results: int = 4,
) -> str:
    """
    Embed the question, query ChromaDB filtered by class+spec (and optionally source),
    and return a formatted context string ready for an LLM prompt.
    """
    if sources is None:
        sources = ["icy_veins", "wowhead"]

    store = get_vector_store()

    # Build ChromaDB where clause
    conditions: list[dict] = [
        {"class": {"$eq": class_name}},
        {"spec": {"$eq": spec}},
    ]
    if len(sources) == 1:
        conditions.append({"source": {"$eq": sources[0]}})
    elif len(sources) > 1:
        conditions.append({"source": {"$in": sources}})

    where = {"$and": conditions}

    try:
        results = store.query(question, filters=where, n_results=n_results)
    except Exception as e:
        logger.error(f"Knowledge base query error: {e}")
        return ""

    if not results:
        return ""

    parts = []
    for r in results:
        source_key = r["metadata"].get("source", "")
        source_label = _SOURCE_LABELS.get(source_key, source_key.replace("_", " ").title())
        topic = r["metadata"].get("topic", "")
        header = f"Source: {source_label}" + (f" ({topic})" if topic else "")
        parts.append(f"{header}\n{r['text']}")

    return "\n\n".join(parts)
