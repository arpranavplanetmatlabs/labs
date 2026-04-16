import os
import hashlib
from pathlib import Path
from typing import List, Set, Dict, Any, Generator
from datetime import datetime
import logging

from db import get_connection
from job_queue import get_job_queue

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc'}

def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file to detect duplicates."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in 64kb chunks
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class MaterialCrawler:
    def __init__(self):
        self.job_queue = get_job_queue()
        self.scanned_count = 0
        self.queued_count = 0
        self.duplicate_count = 0

    def scan_recursive(self, root_path: str) -> Generator[Dict[str, Any], None, None]:
        """
        Recursively scan a folder for material documents and queue them.
        Returns a generator of status updates.
        """
        root = Path(root_path)
        if not root.exists() or not root.is_dir():
            yield {"type": "error", "message": f"Invalid path: {root_path}"}
            return

        yield {"type": "status", "message": f"Starting recursive scan of {root_path}..."}

        conn = get_connection()
        
        # Get existing hashes to avoid re-processing
        existing_hashes = set()
        cursor = conn.execute("SELECT file_hash FROM documents WHERE file_hash IS NOT NULL")
        for row in cursor.fetchall():
            existing_hashes.add(row[0])

        for path in root.rglob('*'):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.scanned_count += 1
                
                try:
                    file_hash = calculate_file_hash(path)
                    
                    if file_hash in existing_hashes:
                        self.duplicate_count += 1
                        continue

                    file_size = path.stat().st_size
                    
                    # Create and queue job
                    job = self.job_queue.create_job(
                        filename=path.name,
                        file_path=str(path),
                        file_size=file_size
                    )
                    
                    # Update DB with path and hash immediately to reserve it
                    conn.execute(
                        "INSERT INTO documents (filename, file_path, file_hash, status) VALUES (?, ?, ?, 'queued')",
                        [path.name, str(path), file_hash, "queued"]
                    )
                    
                    self.job_queue.queue_job(job)
                    self.queued_count += 1
                    existing_hashes.add(file_hash)

                    if self.queued_count % 50 == 0:
                        yield {
                            "type": "progress", 
                            "scanned": self.scanned_count, 
                            "queued": self.queued_count,
                            "duplicates": self.duplicate_count,
                            "current_file": path.name
                        }

                except Exception as e:
                    logger.error(f"Error processing {path}: {e}")
                    yield {"type": "warning", "message": f"Failed to scan {path.name}: {str(e)}"}

        # Log completion in scanned_folders
        conn.execute(
            "INSERT OR REPLACE INTO scanned_folders (folder_path, last_scanned, file_count) VALUES (?, ?, ?)",
            [str(root), datetime.now().isoformat(), self.queued_count]
        )
        conn.close()

        yield {
            "type": "summary",
            "total_scanned": self.scanned_count,
            "total_queued": self.queued_count,
            "total_duplicates": self.duplicate_count,
            "message": f"Scan complete. Queued {self.queued_count} new files. Skipped {self.duplicate_count} duplicates."
        }

def start_recursive_scan(root_path: str):
    crawler = MaterialCrawler()
    return crawler.scan_recursive(root_path)
