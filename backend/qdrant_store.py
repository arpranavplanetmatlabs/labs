"""
qdrant_store.py — Direct Qdrant storage layer replacing DuckDB.

Collections (all payloads are FLAT — no nested 'metadata' key):
  documents          — one entry per file (manifest)
  doc_chunks         — one vector per text chunk (primary search target)
  material_properties — structured property rows
  experiments        — autonomous loop results
  knowledge_edges    — knowledge graph edges
  scanned_folders    — folder watch registry (1-dim dummy)
  job_status         — managed by job_queue.py (unchanged)
"""

import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
    Filter,
    FieldCondition,
    MatchValue,
)
from langchain_ollama import OllamaEmbeddings

from config import (
    QDRANT_URL,
    OLLAMA_BASE,
    EMBED_MODEL,
    COLL_DOCUMENTS,
    COLL_CHUNKS,
    COLL_PROPERTIES,
    COLL_EXPERIMENTS,
    COLL_EDGES,
    COLL_FOLDERS,
    COLL_CHAT_SESSIONS,
)

logger = logging.getLogger(__name__)

EMBED_DIM = 768
CHUNK_SIZE_CHARS = 2000  # ~512 tokens @ 4 chars/token
CHUNK_OVERLAP_CHARS = 200


def calculate_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
    except Exception:
        return ""
    return sha256.hexdigest()


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL)
        self.embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE)
        self._ensure_collections()

    # ── Collection setup ─────────────────────────────────────────────────────

    def _ensure_collections(self):
        try:
            existing = {c.name for c in self.client.get_collections().collections}

            for name in (
                COLL_DOCUMENTS,
                COLL_CHUNKS,
                COLL_PROPERTIES,
                COLL_EXPERIMENTS,
                COLL_EDGES,
            ):
                if name not in existing:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(
                            size=EMBED_DIM, distance=Distance.COSINE
                        ),
                    )
                    logger.info(f"Created collection: {name}")

            if COLL_FOLDERS not in existing:
                self.client.create_collection(
                    collection_name=COLL_FOLDERS,
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE),
                )
                logger.info(f"Created collection: {COLL_FOLDERS}")

            # Chat sessions collection (no vectors, payload-only storage)
            if COLL_CHAT_SESSIONS not in existing:
                self.client.create_collection(
                    collection_name=COLL_CHAT_SESSIONS,
                    vectors_config=VectorParams(
                        size=1, distance=Distance.COSINE
                    ),  # Dummy vector for compatibility
                )
                logger.info(f"Created collection: {COLL_CHAT_SESSIONS}")

            self._create_payload_indexes()
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collections: {e}")
            print(f"WARNING: Qdrant setup failed — search features disabled. ({e})")

    def _create_payload_indexes(self):
        specs = [
            (COLL_DOCUMENTS, "file_hash"),
            (COLL_DOCUMENTS, "doc_type"),
            (COLL_DOCUMENTS, "status"),
            (COLL_DOCUMENTS, "material_name"),
            (COLL_CHUNKS, "doc_id"),
            (COLL_CHUNKS, "material_name"),
            (COLL_PROPERTIES, "doc_id"),
            (COLL_PROPERTIES, "property_name"),
            (COLL_PROPERTIES, "material_name"),
            (COLL_EXPERIMENTS, "iteration"),
            (COLL_EXPERIMENTS, "status"),
            (COLL_EDGES, "source_node"),
            (COLL_EDGES, "target_node"),
            (COLL_EDGES, "edge_type"),
        ]
        for collection, field in specs:
            try:
                self.client.create_payload_index(
                    collection_name=collection,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # Already exists or collection doesn't exist yet

    # ── Embedding helpers ─────────────────────────────────────────────────────

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)

    def _embed_query(self, text: str) -> List[float]:
        return self.embeddings.embed_query(text[:500])

    # ── Text chunking for embedding ───────────────────────────────────────────

    def _split_for_embedding(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE_CHARS, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
        return chunks

    # ── Document manifest ─────────────────────────────────────────────────────

    def upsert_document(
        self,
        doc_id: str,
        filename: str,
        file_path: str,
        file_hash: str,
        doc_type: str,
        material_name: str,
        extraction_confidence: float,
        properties_count: int,
        summary_text: str,
        methodology: str = "",
        research_objective: str = "",
        key_findings: list = None,
        processing_conditions: list = None,
    ) -> str:
        vector = self._embed_query(summary_text)
        payload = {
            "doc_id": doc_id,
            "filename": filename,
            "file_path": file_path,
            "file_hash": file_hash,
            "doc_type": doc_type,
            "material_name": material_name,
            "extraction_confidence": extraction_confidence,
            "properties_count": properties_count,
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "methodology": methodology or "",
            "research_objective": research_objective or "",
            "key_findings": json.dumps(key_findings or []),
            "processing_conditions": json.dumps(processing_conditions or []),
        }
        self.client.upsert(
            collection_name=COLL_DOCUMENTS,
            points=[PointStruct(id=doc_id, vector=vector, payload=payload)],
        )
        return doc_id

    def get_document_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_DOCUMENTS,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="file_hash", match=MatchValue(value=file_hash)
                        )
                    ]
                ),
                limit=1,
                with_vectors=False,
            )
            if results:
                return results[0].payload
        except Exception as e:
            logger.error(f"get_document_by_hash error: {e}")
        return None

    def get_all_documents(self, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_DOCUMENTS,
                limit=limit,
                with_vectors=False,
            )
            return [{"id": p.id, "payload": p.payload} for p in results]
        except Exception as e:
            logger.error(f"get_all_documents error: {e}")
            return []

    def count_documents(self) -> int:
        try:
            return self.client.count(collection_name=COLL_DOCUMENTS).count
        except Exception:
            return 0

    def delete_document_by_id(self, doc_id: str) -> bool:
        try:
            # Delete chunks
            chunk_ids = self._scroll_ids(COLL_CHUNKS, "doc_id", doc_id)
            if chunk_ids:
                self.client.delete(
                    collection_name=COLL_CHUNKS, points_selector=chunk_ids
                )
            # Delete properties
            prop_ids = self._scroll_ids(COLL_PROPERTIES, "doc_id", doc_id)
            if prop_ids:
                self.client.delete(
                    collection_name=COLL_PROPERTIES, points_selector=prop_ids
                )
            # Delete document manifest
            self.client.delete(collection_name=COLL_DOCUMENTS, points_selector=[doc_id])
            return True
        except Exception as e:
            logger.error(f"delete_document_by_id error: {e}")
            return False

    def _scroll_ids(self, collection: str, field: str, value: str) -> List[str]:
        try:
            results, _ = self.client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key=field, match=MatchValue(value=value))]
                ),
                limit=1000,
                with_vectors=False,
            )
            return [str(p.id) for p in results]
        except Exception:
            return []

    # ── Chunks (primary search target) ───────────────────────────────────────

    def upsert_chunks(
        self,
        doc_id: str,
        filename: str,
        doc_type: str,
        material_name: str,
        full_text: str,
    ) -> int:
        """Split text into chunks, embed individually, store in doc_chunks. Returns chunk count."""
        text_chunks = self._split_for_embedding(full_text)
        if not text_chunks:
            raise ValueError(f"No text chunks produced for {filename}")

        vectors = self._embed_texts(text_chunks)
        points = []
        for i, (chunk_text, vector) in enumerate(zip(text_chunks, vectors)):
            chunk_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "filename": filename,
                        "doc_type": doc_type,
                        "material_name": material_name,
                        "content": chunk_text,
                        "chunk_index": i,
                        "total_chunks": len(text_chunks),
                        "created_at": datetime.now().isoformat(),
                    },
                )
            )

        self.client.upsert(collection_name=COLL_CHUNKS, points=points)
        return len(text_chunks)

    def search_chunks(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        vector = self._embed_query(query)
        try:
            results = self.client.search(
                collection_name=COLL_CHUNKS,
                query_vector=vector,
                limit=limit,
                with_payload=True,
            )
            return [
                {
                    "id": str(r.id),
                    "score": r.score,
                    "filename": r.payload.get("filename", ""),
                    "doc_type": r.payload.get("doc_type", ""),
                    "material_name": r.payload.get("material_name", ""),
                    "content": r.payload.get("content", ""),
                    "chunk_index": r.payload.get("chunk_index", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"search_chunks error: {e}")
            return []

    def count_chunks(self) -> int:
        try:
            return self.client.count(collection_name=COLL_CHUNKS).count
        except Exception:
            return 0

    def get_chunks_text_for_doc(self, doc_id: str) -> str:
        """Reconstruct full text from stored chunks for a document."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_CHUNKS,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=500,
                with_vectors=False,
            )
            # Sort by chunk_index and join
            sorted_chunks = sorted(
                results, key=lambda p: p.payload.get("chunk_index", 0)
            )
            return " ".join(p.payload.get("content", "") for p in sorted_chunks)
        except Exception as e:
            logger.error(f"get_chunks_text_for_doc error: {e}")
            return ""

    def update_document_properties_count(
        self,
        doc_id: str,
        properties_count: int,
        material_name: str = None,
        extraction_confidence: float = None,
        methodology: str = None,
        research_objective: str = None,
        key_findings: list = None,
        processing_conditions: list = None,
    ) -> None:
        """Update properties_count (and optionally other extraction fields) on a document manifest."""
        try:
            payload_update: Dict[str, Any] = {"properties_count": properties_count}
            if material_name is not None:
                payload_update["material_name"] = material_name
            if extraction_confidence is not None:
                payload_update["extraction_confidence"] = extraction_confidence
            if methodology is not None:
                payload_update["methodology"] = methodology
            if research_objective is not None:
                payload_update["research_objective"] = research_objective
            if key_findings is not None:
                payload_update["key_findings"] = json.dumps(key_findings)
            if processing_conditions is not None:
                payload_update["processing_conditions"] = json.dumps(processing_conditions)
            self.client.set_payload(
                collection_name=COLL_DOCUMENTS,
                payload=payload_update,
                points=[doc_id],
            )
        except Exception as e:
            logger.error(f"update_document_properties_count error: {e}")

    # ── Properties ───────────────────────────────────────────────────────────

    def upsert_property(
        self,
        doc_id: str,
        filename: str,
        material_name: str,
        property_name: str,
        value: Any,
        unit: str,
        confidence: float,
        context: str,
    ) -> str:
        prop_id = str(uuid.uuid4())
        text = f"{material_name} {property_name}: {value} {unit}"
        vector = self._embed_query(text)
        payload = {
            "doc_id": doc_id,
            "filename": filename,
            "material_name": material_name,
            "property_name": property_name,
            "value": str(value),
            "unit": unit,
            "confidence": confidence,
            "context": context[:300] if context else "",
            "created_at": datetime.now().isoformat(),
        }
        self.client.upsert(
            collection_name=COLL_PROPERTIES,
            points=[PointStruct(id=prop_id, vector=vector, payload=payload)],
        )
        return prop_id

    def get_properties_for_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_PROPERTIES,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=500,
                with_vectors=False,
            )
            return [p.payload for p in results]
        except Exception as e:
            logger.error(f"get_properties_for_doc error: {e}")
            return []

    # ── Experiments ──────────────────────────────────────────────────────────

    def upsert_experiment(
        self,
        exp_id: str,
        name: str,
        goal: str,
        iteration: int,
        material_name: str,
        candidates: List[Dict],
        best_candidate: Dict,
        reasoning: str,
        composite_score: float,
    ) -> str:
        text = f"{name}: {goal[:200]} — {reasoning[:200]}"
        vector = self._embed_query(text)
        payload = {
            "exp_id": exp_id,
            "name": name,
            "goal": goal,
            "iteration": str(iteration),
            "material_name": material_name,
            "candidates": json.dumps(candidates),
            "best_candidate": json.dumps(best_candidate),
            "reasoning": reasoning,
            "composite_score": composite_score,
            "status": "completed",
            "created_at": datetime.now().isoformat(),
        }
        self.client.upsert(
            collection_name=COLL_EXPERIMENTS,
            points=[PointStruct(id=exp_id, vector=vector, payload=payload)],
        )
        return exp_id

    def get_recent_experiments(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_EXPERIMENTS,
                limit=limit,
                with_vectors=False,
            )
            payloads = [p.payload for p in results]
            payloads.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return payloads
        except Exception as e:
            logger.error(f"get_recent_experiments error: {e}")
            return []

    def count_experiments(self) -> int:
        try:
            return self.client.count(collection_name=COLL_EXPERIMENTS).count
        except Exception:
            return 0

    # ── Folders (crawler registry) ────────────────────────────────────────────

    def upsert_folder(self, folder_path: str, file_count: int):
        folder_id = str(uuid.uuid5(uuid.NAMESPACE_URL, folder_path))
        payload = {
            "folder_path": folder_path,
            "file_count": file_count,
            "last_scanned": datetime.now().isoformat(),
        }
        self.client.upsert(
            collection_name=COLL_FOLDERS,
            points=[PointStruct(id=folder_id, vector=[0.0], payload=payload)],
        )

    def get_all_file_hashes(self) -> set:
        """Return set of all known file hashes for deduplication."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_DOCUMENTS,
                limit=10000,
                with_vectors=False,
            )
            return {
                p.payload.get("file_hash", "")
                for p in results
                if p.payload.get("file_hash")
            }
        except Exception:
            return set()

    # ── Knowledge graph edges ─────────────────────────────────────────────────

    def upsert_edge(
        self,
        source_node: str,
        target_node: str,
        edge_type: str,
        weight: float = 1.0,
        metadata: Dict = None,
    ) -> str:
        edge_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{source_node}→{target_node}→{edge_type}")
        )
        text = f"{source_node} {edge_type} {target_node}"
        vector = self._embed_query(text)
        payload = {
            "source_node": source_node,
            "target_node": target_node,
            "edge_type": edge_type,
            "weight": weight,
            "metadata": json.dumps(metadata or {}),
            "created_at": datetime.now().isoformat(),
        }
        self.client.upsert(
            collection_name=COLL_EDGES,
            points=[PointStruct(id=edge_id, vector=vector, payload=payload)],
        )
        return edge_id

    def get_all_edges(self, limit: int = 5000) -> List[Dict[str, Any]]:
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_EDGES, limit=limit, with_vectors=False
            )
            return [p.payload for p in results]
        except Exception as e:
            logger.error(f"get_all_edges error: {e}")
            return []

    # ── Chat Sessions (persistent storage) ─────────────────────────────────────

    def _generate_session_uuid(self, session_id: str) -> str:
        """Generate a valid UUID from session_id string."""
        if session_id == "default":
            return "00000000-0000-0000-0000-000000000000"
        try:
            uuid.UUID(session_id)
            return session_id
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, session_id))

    def upsert_chat_session(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        role: str = "scientist",
    ) -> bool:
        """Save or update a chat session."""
        try:
            point_id = self._generate_session_uuid(session_id)
            payload = {
                "session_id": session_id,
                "messages": json.dumps(messages),
                "role": role,
                "created_at": messages[0].get("timestamp", datetime.now().isoformat())
                if messages
                else datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "message_count": len(messages),
            }
            self.client.upsert(
                collection_name=COLL_CHAT_SESSIONS,
                points=[PointStruct(id=point_id, vector=[0.0], payload=payload)],
            )
            return True
        except Exception as e:
            logger.error(f"upsert_chat_session error: {e}")
            return False

    def get_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a chat session by ID."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_CHAT_SESSIONS,
                limit=1,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id", match=MatchValue(value=session_id)
                        )
                    ]
                ),
                with_vectors=False,
            )
            if results:
                payload = results[0].payload
                payload["messages"] = json.loads(payload.get("messages", "[]"))
                return payload
            return None
        except Exception as e:
            logger.error(f"get_chat_session error: {e}")
            return None

    def get_all_chat_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all chat sessions, ordered by last active."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_CHAT_SESSIONS,
                limit=limit,
                with_vectors=False,
            )
            sessions = []
            for p in results:
                payload = p.payload
                payload["messages"] = json.loads(payload.get("messages", "[]"))
                sessions.append(payload)
            return sorted(
                sessions, key=lambda x: x.get("last_active", ""), reverse=True
            )
        except Exception as e:
            logger.error(f"get_all_chat_sessions error: {e}")
            return []

    def delete_chat_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        try:
            self.client.delete(
                collection_name=COLL_CHAT_SESSIONS,
                points_selector=[session_id],
            )
            return True
        except Exception as e:
            logger.error(f"delete_chat_session error: {e}")
            return False

    # ── Experiments (persistent storage) ─────────────────────────────────────

    def upsert_experiment(
        self,
        experiment_id: int,
        name: str,
        material_name: str,
        description: str,
        conditions: Dict[str, Any],
        expected_output: Dict[str, Any],
        actual_output: Dict[str, Any],
        results: List[Dict[str, Any]],
        status: str,
        confidence_score: float,
        predictions: Dict[str, Any],
        suggestions: List[Dict[str, Any]],
    ) -> bool:
        """Save or update an experiment."""
        try:
            # Generate content for embedding
            content = f"{name} {material_name} {description} {json.dumps(conditions)} {json.dumps(expected_output)}"

            # Generate embedding for search
            vector = self.embeddings.embed_query(content[:500])

            payload = {
                "experiment_id": experiment_id,
                "name": name,
                "material_name": material_name,
                "description": description,
                "conditions": json.dumps(conditions),
                "expected_output": json.dumps(expected_output),
                "actual_output": json.dumps(actual_output),
                "results": json.dumps(results),
                "status": status,
                "confidence_score": confidence_score,
                "predictions": json.dumps(predictions) if predictions else None,
                "suggestions": json.dumps(suggestions) if suggestions else None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self.client.upsert(
                collection_name=COLL_EXPERIMENTS,
                points=[PointStruct(id=experiment_id, vector=vector, payload=payload)],
            )
            return True
        except Exception as e:
            logger.error(f"upsert_experiment error: {e}")
            return False

    def get_experiment(self, experiment_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve an experiment by ID."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_EXPERIMENTS,
                limit=1,
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="experiment_id", match=MatchValue(value=experiment_id)
                        )
                    ]
                ),
                with_vectors=False,
            )
            if results:
                payload = results[0].payload
                # Parse JSON fields
                for field in [
                    "conditions",
                    "expected_output",
                    "actual_output",
                    "results",
                    "predictions",
                    "suggestions",
                ]:
                    if payload.get(field):
                        try:
                            payload[field] = json.loads(payload[field])
                        except:
                            pass
                return payload
            return None
        except Exception as e:
            logger.error(f"get_experiment error: {e}")
            return None

    def get_all_experiments(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all experiments."""
        try:
            results, _ = self.client.scroll(
                collection_name=COLL_EXPERIMENTS,
                limit=limit,
                with_vectors=False,
            )
            experiments = []
            for p in results:
                payload = p.payload
                # Parse JSON fields
                for field in [
                    "conditions",
                    "expected_output",
                    "actual_output",
                    "results",
                    "predictions",
                    "suggestions",
                ]:
                    if payload.get(field):
                        try:
                            payload[field] = json.loads(payload[field])
                        except:
                            pass
                experiments.append(payload)
            return sorted(
                experiments, key=lambda x: x.get("created_at", ""), reverse=True
            )
        except Exception as e:
            logger.error(f"get_all_experiments error: {e}")
            return []

    def delete_experiment(self, experiment_id: int) -> bool:
        """Delete an experiment."""
        try:
            self.client.delete(
                collection_name=COLL_EXPERIMENTS,
                points_selector=[experiment_id],
            )
            return True
        except Exception as e:
            logger.error(f"delete_experiment error: {e}")
            return False

    def search_experiments(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search over experiments."""
        try:
            vector = self.embeddings.embed_query(query)
            results = self.client.search(
                collection_name=COLL_EXPERIMENTS,
                query_vector=vector,
                limit=limit,
            )
            experiments = []
            for r in results:
                payload = r.payload
                payload["score"] = r.score
                # Parse JSON fields
                for field in [
                    "conditions",
                    "expected_output",
                    "actual_output",
                    "results",
                    "predictions",
                    "suggestions",
                ]:
                    if payload.get(field):
                        try:
                            payload[field] = json.loads(payload[field])
                        except:
                            pass
                experiments.append(payload)
            return experiments
        except Exception as e:
            logger.error(f"search_experiments error: {e}")
            return []


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: Optional[QdrantStore] = None


def get_store() -> QdrantStore:
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store
