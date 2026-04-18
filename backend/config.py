import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PARSED_DIR = DATA_DIR / "parsed"
QDRANT_DIR = DATA_DIR / "qdrant_storage"
DB_PATH = DATA_DIR / "research.db"  # Kept for backward compatibility

DATA_DIR.mkdir(exist_ok=True)
PARSED_DIR.mkdir(exist_ok=True)
QDRANT_DIR.mkdir(exist_ok=True)

OLLAMA_BASE = "http://localhost:11434"
LLM_MODEL = "qwen2.5:3b-instruct-q4_K_S"
EMBED_MODEL = "nomic-embed-text"

QDRANT_URL = "http://localhost:6333"
QDRANT_PATH = str(QDRANT_DIR)

_qdrant_client = None

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
        
    from qdrant_client import QdrantClient
    try:
        # Try server mode first
        client = QdrantClient(url=QDRANT_URL, timeout=1)
        client.get_collections() # Quick connectivity test
        _qdrant_client = client
        return _qdrant_client
    except Exception:
        # Fallback to local mode
        _qdrant_client = QdrantClient(path=QDRANT_PATH)
        return _qdrant_client

# Qdrant collection names
QDRANT_COLLECTION = "parsed_materials"  # Legacy — kept for search compatibility
COLL_DOCUMENTS = "documents"  # One entry per file (manifest)
COLL_CHUNKS = "doc_chunks"  # One vector per text chunk (primary search)
COLL_PROPERTIES = "material_properties"  # Structured property rows
COLL_EXPERIMENTS = "experiments"  # Autonomous loop results
COLL_EDGES = "knowledge_edges"  # Knowledge graph edges
COLL_FOLDERS = "scanned_folders"  # Folder watch registry
COLL_JOBS = "job_status"  # Ingestion job tracking
COLL_CHAT_SESSIONS = "chat_sessions"  # Chat session history (new)
COLL_SCHEMAS = "experiment_schemas"   # Phase 7: BO experiment schema definitions

GRAPH_CACHE_TTL = 300  # Seconds before knowledge graph is rebuilt from Qdrant

# Phase 7: surrogate model persistence directory
SURROGATE_DIR = DATA_DIR / "surrogates"
SURROGATE_DIR.mkdir(exist_ok=True)

API_PORT = 8000
