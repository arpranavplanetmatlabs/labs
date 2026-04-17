import os
import sys
import sqlite3
import shutil
from pathlib import Path

# Try to import psutil, install if missing (but I'll try to use taskkill as fallback)
try:
    import psutil
except ImportError:
    print("psutil not found, using taskkill fallback...")
    psutil = None

from qdrant_client import QdrantClient

# Ensure we are in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import config constants
sys.path.append(os.getcwd())
try:
    from config import (
        QDRANT_URL, COLL_DOCUMENTS, COLL_CHUNKS, COLL_PROPERTIES, 
        COLL_EXPERIMENTS, COLL_EDGES, COLL_FOLDERS, COLL_JOBS, 
        COLL_CHAT_SESSIONS, DATA_DIR, DB_PATH
    )
except ImportError:
    print("Could not import config. Using defaults.")
    QDRANT_URL = "http://localhost:6333"
    COLL_DOCUMENTS = "documents"
    COLL_CHUNKS = "doc_chunks"
    COLL_PROPERTIES = "material_properties"
    COLL_EXPERIMENTS = "experiments"
    COLL_EDGES = "knowledge_edges"
    COLL_FOLDERS = "scanned_folders"
    COLL_JOBS = "job_status"
    COLL_CHAT_SESSIONS = "chat_sessions"
    DATA_DIR = Path("data")
    DB_PATH = DATA_DIR / "research.db"

def kill_python_processes():
    print("Stopping python processes...")
    if psutil:
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if it's a python process and not this script
                if proc.info['pid'] != current_pid and ('python' in proc.info['name'].lower()):
                    # Check if it's running main.py or uvicorn
                    cmdline = proc.info['cmdline'] or []
                    if any('main.py' in part for part in cmdline) or any('uvicorn' in part for part in cmdline):
                        print(f"Killing process {proc.info['pid']}: {cmdline}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    else:
        # Fallback to taskkill
        os.system('taskkill /F /IM python.exe /T')

def clear_qdrant():
    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    try:
        client = QdrantClient(url=QDRANT_URL)
        
        collections = [
            COLL_DOCUMENTS, COLL_CHUNKS, COLL_PROPERTIES, 
            COLL_EXPERIMENTS, COLL_EDGES, COLL_FOLDERS, 
            COLL_JOBS, COLL_CHAT_SESSIONS, "parsed_materials"
        ]
        
        for coll in collections:
            try:
                print(f"Deleting collection: {coll}")
                client.delete_collection(collection_name=coll)
            except Exception as e:
                print(f"Skipped {coll}: {e}")
    except Exception as e:
        print(f"Qdrant connection error: {e}")

def clear_data_folders():
    print("Clearing data folders...")
    uploads_dir = DATA_DIR / "uploads"
    if uploads_dir.exists():
        try:
            shutil.rmtree(uploads_dir)
            uploads_dir.mkdir(parents=True, exist_ok=True)
            print("Cleared uploads folder.")
        except Exception as e:
            print(f"Error clearing uploads: {e}")
    
    # Also delete the DuckDB database if it exists
    if DB_PATH.exists():
        try:
            os.remove(DB_PATH)
            print(f"Deleted DuckDB database: {DB_PATH}")
        except Exception as e:
            print(f"Error deleting DB: {e}")

if __name__ == "__main__":
    kill_python_processes()
    clear_qdrant()
    clear_data_folders()
    print("\nSystem refreshed! Status: CLEAN")
