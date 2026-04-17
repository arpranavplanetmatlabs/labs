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
LLM_MODEL = "qwen2.5:14b-instruct-q4_K_S"
EMBED_MODEL = "nomic-embed-text"

QDRANT_URL = "http://localhost:6333"

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

GRAPH_CACHE_TTL = 300  # Seconds before knowledge graph is rebuilt from Qdrant

API_PORT = 8000
