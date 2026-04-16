import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PARSED_DIR = DATA_DIR / "parsed"
QDRANT_DIR = DATA_DIR / "qdrant_storage"
DB_PATH = DATA_DIR / "research.db"

DATA_DIR.mkdir(exist_ok=True)
PARSED_DIR.mkdir(exist_ok=True)
QDRANT_DIR.mkdir(exist_ok=True)

OLLAMA_BASE = "http://localhost:11434"
LLM_MODEL = "qwen2.5:14b-instruct-q4_K_S"  # Upgraded from 3b for better reasoning
EMBED_MODEL = "nomic-embed-text"

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "parsed_materials"

API_PORT = 8000
