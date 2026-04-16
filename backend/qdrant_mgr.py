from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from langchain_qdrant import QdrantVectorStore
from langchain_ollama import OllamaEmbeddings
from typing import List, Dict, Any, Optional
import json
import uuid
import logging

from config import QDRANT_URL, QDRANT_COLLECTION, OLLAMA_BASE, EMBED_MODEL

logger = logging.getLogger(__name__)


class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL)
        self.embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE)
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if QDRANT_COLLECTION not in collection_names:
                self.client.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                print(f"Created Qdrant collection: {QDRANT_COLLECTION}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant or ensure collection: {e}")
            print(f"WARNING: Qdrant at {QDRANT_URL} is offline. Search features will be disabled.")

    def get_vectorstore(self) -> Optional[QdrantVectorStore]:
        try:
            return QdrantVectorStore(
                client=self.client,
                collection_name=QDRANT_COLLECTION,
                embedding=self.embeddings,
            )
        except Exception as e:
            logger.error(f"Failed to get Qdrant vectorstore: {e}")
            return None

    def add_document(
        self,
        filename: str,
        doc_type: str,
        content: str,
        metadata: Dict[str, Any],
        doc_id: Optional[int] = None,
    ) -> Optional[str]:
        vectorstore = self.get_vectorstore()
        if not vectorstore:
            return None

        point_id = str(uuid.uuid4())

        try:
            vectorstore.add_texts(
                texts=[content],
                ids=[point_id],
                metadatas=[
                    {
                        "point_id": point_id,
                        "filename": filename,
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        **metadata,
                    }
                ],
            )
            return point_id
        except Exception as e:
            logger.error(f"Failed to add document to Qdrant: {e}")
            return None

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        vectorstore = self.get_vectorstore()
        if not vectorstore:
            return []

        try:
            results = vectorstore.similarity_search_with_score(query=query, k=limit)

            return [
                {
                    "id": doc.metadata.get("point_id"),
                    "filename": doc.metadata.get("filename"),
                    "doc_type": doc.metadata.get("doc_type"),
                    "content": doc.page_content[:500],
                    "score": score,
                    "metadata": {k: v for k, v in doc.metadata.items() if k != "point_id"},
                }
                for doc, score in results
            ]
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def get_all_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            results = self.client.scroll(
                collection_name=QDRANT_COLLECTION, limit=limit, with_vectors=False
            )

            documents = []
            for point in results[0]:
                raw = point.payload or {}
                # LangChain stores metadata nested under a "metadata" key.
                # Flatten it to the top level so callers can access filename, doc_type etc. directly.
                nested_meta = raw.get("metadata", {})
                flat_payload = {**raw, **nested_meta}
                documents.append({"id": point.id, "payload": flat_payload})
            return documents
        except Exception as e:
            logger.error(f"Failed to get documents from Qdrant: {e}")
            return []

    def delete_document(self, point_id: str) -> bool:
        try:
            self.client.delete(
                collection_name=QDRANT_COLLECTION, points_selector=[point_id]
            )
            return True
        except Exception as e:
            print(f"Delete error: {e}")
            return False

    def delete_all(self) -> bool:
        try:
            self.client.delete_collection(QDRANT_COLLECTION)
            self._ensure_collection()
            return True
        except Exception as e:
            print(f"Delete all error: {e}")
            return False


def get_qdrant_manager() -> QdrantManager:
    return QdrantManager()

