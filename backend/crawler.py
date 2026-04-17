"""
crawler.py — Recursive folder scanner using Qdrant for dedup and folder registry.
DuckDB removed — file hash deduplication via qdrant_store.get_all_file_hashes().
"""

import logging
from pathlib import Path
from typing import Generator, Dict, Any
from datetime import datetime

from qdrant_store import get_store, calculate_file_hash
from job_queue import get_job_queue

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc'}


class MaterialCrawler:
    def __init__(self):
        self.job_queue = get_job_queue()
        self.scanned_count = 0
        self.queued_count = 0
        self.duplicate_count = 0

    def scan_recursive(self, root_path: str) -> Generator[Dict[str, Any], None, None]:
        root = Path(root_path)
        if not root.exists() or not root.is_dir():
            yield {"type": "error", "message": f"Invalid path: {root_path}"}
            return

        yield {"type": "status", "message": f"Starting recursive scan of {root_path}..."}

        store = get_store()
        existing_hashes = store.get_all_file_hashes()

        for path in root.rglob('*'):
            if not (path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS):
                continue

            self.scanned_count += 1

            try:
                file_hash = calculate_file_hash(str(path))

                if file_hash in existing_hashes:
                    self.duplicate_count += 1
                    continue

                file_size = path.stat().st_size
                job = self.job_queue.create_job(
                    filename=path.name,
                    file_path=str(path),
                    file_size=file_size,
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
                        "current_file": path.name,
                    }

            except Exception as e:
                logger.error(f"Error processing {path}: {e}")
                yield {"type": "warning", "message": f"Failed to scan {path.name}: {str(e)}"}

        # Register folder in Qdrant
        try:
            store.upsert_folder(str(root), self.queued_count)
        except Exception as e:
            logger.warning(f"Failed to register folder: {e}")

        yield {
            "type": "summary",
            "total_scanned": self.scanned_count,
            "total_queued": self.queued_count,
            "total_duplicates": self.duplicate_count,
            "message": f"Scan complete. Queued {self.queued_count} new files. Skipped {self.duplicate_count} duplicates.",
        }


def start_recursive_scan(root_path: str):
    crawler = MaterialCrawler()
    return crawler.scan_recursive(root_path)
