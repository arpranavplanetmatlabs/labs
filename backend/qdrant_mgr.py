"""
qdrant_mgr.py — Qdrant manager with graph-aware search.

search() now uses knowledge_graph.graph_aware_search() (vector seed + 2-hop
NetworkX expansion + combined re-ranking) instead of flat cosine similarity.

add_document() is kept for backward compatibility with upload paths but delegates
to qdrant_store for flat payload storage.
"""

import logging
from typing import List, Dict, Any, Optional

from config import QDRANT_URL, QDRANT_COLLECTION
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


class QdrantManager:
    def __init__(self):
        from config import get_qdrant_client
        self.client = get_qdrant_client()

    # ── Primary search (graph-aware) ──────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Graph-aware semantic search over doc_chunks collection.
        Falls back to legacy parsed_materials collection if chunks collection is empty.
        """
        try:
            from knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph()
            results = kg.graph_aware_search(query=query, k=limit)
            if results:
                return results
        except Exception as e:
            logger.warning(f"Graph-aware search failed, falling back to legacy: {e}")

        # Legacy fallback: search parsed_materials via LangChain vectorstore
        return self._legacy_search(query, limit)

    def _legacy_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search the old parsed_materials collection (LangChain format)."""
        try:
            from langchain_ollama import OllamaEmbeddings
            from langchain_qdrant import QdrantVectorStore
            from config import OLLAMA_BASE, EMBED_MODEL

            embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE)
            collections = {c.name for c in self.client.get_collections().collections}
            if QDRANT_COLLECTION not in collections:
                return []

            vectorstore = QdrantVectorStore(
                client=self.client,
                collection_name=QDRANT_COLLECTION,
                embedding=embeddings,
            )
            raw = vectorstore.similarity_search_with_score(query=query, k=limit)
            results = []
            for doc, score in raw:
                # Flatten LangChain nested metadata
                meta = doc.metadata.get("metadata", doc.metadata)
                results.append({
                    "id": meta.get("point_id"),
                    "filename": meta.get("filename", ""),
                    "doc_type": meta.get("doc_type", ""),
                    "content": doc.page_content[:500],
                    "material_name": meta.get("material_name", ""),
                    "score": score,
                })
            return results
        except Exception as e:
            logger.error(f"Legacy search error: {e}")
            return []

    # ── Document addition (delegates to qdrant_store) ─────────────────────────

    def add_document(
        self,
        filename: str,
        doc_type: str,
        content: str,
        metadata: Dict[str, Any],
        doc_id: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Thin wrapper for backward compatibility.
        Stores a single chunk in doc_chunks via qdrant_store.
        New code should call qdrant_store.upsert_document() + upsert_chunks() directly.
        """
        try:
            from qdrant_store import get_store
            import uuid

            store = get_store()
            new_doc_id = str(uuid.uuid4())
            material_name = metadata.get("material_name", "")

            store.upsert_document(
                doc_id=new_doc_id,
                filename=filename,
                file_path="",
                file_hash="",
                doc_type=doc_type,
                material_name=material_name,
                extraction_confidence=metadata.get("extraction_confidence", 0.0),
                properties_count=0,
                summary_text=content[:500],
            )
            store.upsert_chunks(
                doc_id=new_doc_id,
                filename=filename,
                doc_type=doc_type,
                material_name=material_name,
                full_text=content,
            )
            return new_doc_id
        except Exception as e:
            logger.error(f"add_document error: {e}")
            return None

    # ── Document listing ──────────────────────────────────────────────────────

    def get_all_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return all documents from the documents collection (flat payload)."""
        try:
            from qdrant_store import get_store
            store = get_store()
            return store.get_all_documents(limit=limit)
        except Exception as e:
            logger.error(f"get_all_documents error: {e}")
            return []

    def delete_document(self, point_id: str) -> bool:
        try:
            from qdrant_store import get_store
            store = get_store()
            return store.delete_document_by_id(point_id)
        except Exception as e:
            logger.error(f"delete_document error: {e}")
            return False

    def delete_all(self) -> bool:
        try:
            self.client.delete_collection(QDRANT_COLLECTION)
            return True
        except Exception as e:
            logger.error(f"delete_all error: {e}")
            return False


def get_qdrant_manager() -> QdrantManager:
    return QdrantManager()
