import hashlib
import logging

import chromadb

logger = logging.getLogger(__name__)

_instance = None


def get_vector_store() -> "VectorStore":
    global _instance
    if _instance is None:
        _instance = VectorStore()
    return _instance


class VectorStore:
    def __init__(self, persist_dir: str = "./chroma_db"):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="wow_guides",
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, docs: list[dict]):
        """
        Each doc: {text, metadata: {source, class, spec, topic, url}}
        """
        if not docs:
            return

        from services.knowledge_base.embedder import embed

        ids, embeddings, documents, metadatas = [], [], [], []
        for doc in docs:
            text = doc["text"]
            meta = doc["metadata"]
            # Deterministic ID so upsert deduplicates on re-ingestion
            raw = f"{meta.get('source')}{meta.get('class')}{meta.get('spec')}{meta.get('topic')}{text[:80]}"
            doc_id = hashlib.md5(raw.encode()).hexdigest()
            ids.append(doc_id)
            embeddings.append(embed(text))
            documents.append(text)
            metadatas.append(meta)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug(f"Upserted {len(docs)} document(s) into ChromaDB.")

    def query(self, text: str, filters: dict, n_results: int = 4) -> list[dict]:
        from services.knowledge_base.embedder import embed

        query_embedding = embed(text)

        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            kwargs["where"] = filters

        try:
            results = self._collection.query(**kwargs)
        except Exception as e:
            logger.warning(f"ChromaDB query failed: {e}")
            return []

        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({"text": doc, "metadata": meta, "distance": dist})
        return output

    def delete_by_source(self, source: str):
        try:
            self._collection.delete(where={"source": source})
            logger.info(f"Deleted documents with source='{source}' from ChromaDB.")
        except Exception as e:
            logger.warning(f"delete_by_source failed for source='{source}': {e}")

    def get_collection_stats(self) -> dict:
        return {
            "collection": "wow_guides",
            "total_chunks": self._collection.count(),
        }
