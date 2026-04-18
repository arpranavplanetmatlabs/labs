"""
job_queue.py - Background Job Queue with Priority and Qdrant Persistence

Features:
- Priority queue (high: <1MB, medium: 1-10MB, low: >10MB)
- Persistent job storage in Qdrant (job_status collection)
- Background worker for async processing
- Qdrant-only storage — no DuckDB
"""

import asyncio
import heapq
import uuid
import json
import time
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import QDRANT_URL
from parser import extract_text
from extractor import extract_from_text, extract_properties_list
from qdrant_store import get_store, calculate_file_hash

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    HIGH = 0    # <1MB
    MEDIUM = 1  # 1-10MB
    LOW = 2     # >10MB


@dataclass
class Job:
    job_id: str
    filename: str
    file_path: str
    file_size: int
    doc_type: str = "pending"
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.MEDIUM
    progress: float = 0.0
    current_step: str = ""
    error_message: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    doc_id: Optional[str] = None
    confidence: float = 0.0
    properties_count: int = 0
    retry_count: int = 0
    max_retries: int = 3
    qdrant_point_id: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "doc_type": self.doc_type,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "priority": self.priority.value if isinstance(self.priority, Enum) else self.priority,
            "progress": self.progress,
            "current_step": self.current_step,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "doc_id": self.doc_id,
            "confidence": self.confidence,
            "properties_count": self.properties_count,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "qdrant_point_id": self.qdrant_point_id,
        }

    @property
    def queue_key(self) -> tuple:
        return (
            self.priority.value if isinstance(self.priority, Enum) else self.priority,
            time.time(),
            self.job_id,
        )


def _extract_material_name_regex(text: str) -> str:
    """Regex fallback for material name extraction."""
    patterns = [
        r'\b([A-Z][A-Za-z]+(?: \d+[A-Za-z]*)?(?:[-/][A-Za-z0-9]+)*)\b(?=.*(?:grade|resin|compound|polymer|rubber|elastomer|nylon|polyamide|polycarbonate|polypropylene|polyethylene|ABS|EPDM|TPU|TPE|POM|PET|PBT|PEEK|PTFE))',
        r'\b(Nylon\s*\d+|PA\s*\d+[A-Z]*|PP[A-Z0-9-]*|PC[A-Z0-9-]*|ABS[A-Z0-9-]*|EPDM[A-Z0-9-]*|TPU[A-Z0-9-]*|POM[A-Z0-9-]*|PEEK[A-Z0-9-]*|PTFE[A-Z0-9-]*|PET[A-Z0-9-]*|PBT[A-Z0-9-]*)\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:2000], re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


class JobQueue:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.high_priority: List = []
        self.medium_priority: List = []
        self.low_priority: List = []

        self.active_jobs: Dict[str, Job] = {}
        self.job_counter = 0

        from config import get_qdrant_client
        self._qdrant_client = get_qdrant_client()
        self._ensure_job_collection()

        self.worker_task: Optional[asyncio.Task] = None
        self._running = False

    def _ensure_job_collection(self):
        try:
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            if "job_status" not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name="job_status",
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE),
                )
                print("Created Qdrant collection: job_status")
        except Exception as e:
            logger.warning(f"job_status collection setup: {e}")

    @staticmethod
    def calculate_priority(file_size: int) -> JobPriority:
        if file_size < 1024 * 1024:
            return JobPriority.HIGH
        elif file_size < 10 * 1024 * 1024:
            return JobPriority.MEDIUM
        else:
            return JobPriority.LOW

    def create_job(self, filename: str, file_path: str, file_size: int) -> Job:
        job_id = str(uuid.uuid4())
        priority = self.calculate_priority(file_size)
        job = Job(
            job_id=job_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            priority=priority,
            created_at=datetime.now().isoformat(),
        )
        self._save_job(job)
        return job

    def queue_job(self, job: Job) -> None:
        job.status = JobStatus.QUEUED
        queue_key = job.queue_key
        if job.priority == JobPriority.HIGH:
            heapq.heappush(self.high_priority, (queue_key, job))
        elif job.priority == JobPriority.MEDIUM:
            heapq.heappush(self.medium_priority, (queue_key, job))
        else:
            heapq.heappush(self.low_priority, (queue_key, job))
        self._save_job(job)
        print(f"[QUEUE] Queued {job.filename} — Priority: {job.priority.name}")

    def get_next_job(self) -> Optional[Job]:
        if self.high_priority:
            _, job = heapq.heappop(self.high_priority)
            return job
        elif self.medium_priority:
            _, job = heapq.heappop(self.medium_priority)
            return job
        elif self.low_priority:
            _, job = heapq.heappop(self.low_priority)
            return job
        return None

    def get_job(self, job_id: str) -> Optional[Job]:
        if job_id in self.active_jobs:
            return self.active_jobs[job_id]
        try:
            results = self._qdrant_client.retrieve(collection_name="job_status", ids=[job_id])
            if results:
                return self._job_from_payload(results[0].payload)
        except Exception:
            pass
        return None

    def get_all_jobs(self, limit: int = 100) -> List[Job]:
        try:
            results, _ = self._qdrant_client.scroll(
                collection_name="job_status", limit=limit, with_vectors=False
            )
            jobs = [self._job_from_payload(p.payload) for p in results if p.payload]
            jobs = [j for j in jobs if j]
            return sorted(jobs, key=lambda j: j.created_at, reverse=True)
        except Exception as e:
            logger.error(f"get_all_jobs error: {e}")
            return []

    def _job_from_payload(self, payload: Dict) -> Optional[Job]:
        try:
            return Job(
                job_id=payload.get("job_id", ""),
                filename=payload.get("filename", ""),
                file_path=payload.get("file_path", ""),
                file_size=payload.get("file_size", 0),
                doc_type=payload.get("doc_type", "pending"),
                status=JobStatus(payload.get("status", "pending")),
                priority=JobPriority(payload.get("priority", 1)),
                progress=payload.get("progress", 0.0),
                current_step=payload.get("current_step", ""),
                error_message=payload.get("error_message", ""),
                created_at=payload.get("created_at", ""),
                started_at=payload.get("started_at", ""),
                completed_at=payload.get("completed_at", ""),
                doc_id=payload.get("doc_id"),
                confidence=payload.get("confidence", 0.0),
                properties_count=payload.get("properties_count", 0),
                retry_count=payload.get("retry_count", 0),
                qdrant_point_id=payload.get("qdrant_point_id"),
            )
        except Exception as e:
            logger.error(f"Error parsing job payload: {e}")
            return None

    def _save_job(self, job: Job) -> None:
        try:
            from qdrant_client.models import PointStruct
            payload = job.to_dict()
            payload["status"] = job.status.value if isinstance(job.status, Enum) else job.status
            payload["priority"] = job.priority.value if isinstance(job.priority, Enum) else job.priority
            self._qdrant_client.upsert(
                collection_name="job_status",
                points=[PointStruct(id=job.job_id, vector=[0.0], payload=payload)],
            )
        except Exception as e:
            logger.error(f"Error saving job: {e}")

    def update_job(self, job: Job) -> None:
        self.active_jobs[job.job_id] = job
        self._save_job(job)

    def cancel_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if not job or job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            return False
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now().isoformat()
        self.update_job(job)
        return True

    def cancel_all_jobs(self) -> int:
        """Cancel all queued/pending/running jobs. Returns count cancelled."""
        cancelled = 0
        # Drain the in-memory priority queues
        for queue in (self.high_priority, self.medium_priority, self.low_priority):
            while queue:
                _, job = heapq.heappop(queue)
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now().isoformat()
                self._save_job(job)
                cancelled += 1
        # Also mark any active jobs (currently running) as cancelled
        # so the worker skips storing results after the current LLM call finishes
        for job in list(self.active_jobs.values()):
            if job.status in [JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PENDING]:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now().isoformat()
                self._save_job(job)
                cancelled += 1
        # Persist cancellation of any queued jobs still only in Qdrant
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            results, _ = self._qdrant_client.scroll(
                collection_name="job_status",
                scroll_filter=Filter(must=[FieldCondition(
                    key="status", match=MatchAny(any=["queued", "pending", "running"]),
                )]),
                limit=200, with_vectors=False,
            )
            for point in results:
                job = self._job_from_payload(point.payload)
                if job and job.status not in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now().isoformat()
                    self._save_job(job)
                    cancelled += 1
        except Exception as e:
            logger.warning(f"cancel_all Qdrant scan failed: {e}")
        print(f"[QUEUE] Cancelled {cancelled} job(s)")
        return cancelled

    async def process_job(self, job: Job) -> Job:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        self.update_job(job)

        print(f"[WORKER] Processing {job.filename}...")

        try:
            # Step 1: Extract text from PDF
            job.current_step = "Extracting text"
            self.update_job(job)
            chunks = await asyncio.to_thread(extract_text, job.file_path)
            all_text = " ".join(c.get("content", "") for c in chunks)

            if not all_text.strip():
                raise ValueError("No text extracted from document")

            # Step 2: LLM extraction (detect type, extract properties, material name)
            job.current_step = "Running LLM extraction"
            self.update_job(job)
            extraction_result = await asyncio.to_thread(extract_from_text, all_text)

            job.doc_type = extraction_result.get("document_type", "paper")
            job.confidence = extraction_result.get("extraction_confidence", 0.0)

            # 3-tier material_name fallback: LLM → regex → filename stem
            material_name = (
                extraction_result.get("material_name", "").strip()
                or _extract_material_name_regex(all_text)
                or Path(job.filename).stem
            )

            properties = extract_properties_list(extraction_result)
            job.properties_count = len(properties)

            # Step 3: Store to Qdrant (failure marks job FAILED — no more silent swallow)
            job.current_step = "Storing in Qdrant"
            self.update_job(job)

            store = get_store()
            doc_id = str(uuid.uuid4())
            file_hash = calculate_file_hash(job.file_path)

            # Pull paper-specific fields from extraction result
            key_findings = extraction_result.get("key_findings", [])
            processing_conditions = extraction_result.get("processing_conditions", [])
            methodology = extraction_result.get("methodology", "")
            research_objective = extraction_result.get("research_objective", "")

            # Upsert document manifest
            store.upsert_document(
                doc_id=doc_id,
                filename=job.filename,
                file_path=job.file_path,
                file_hash=file_hash,
                doc_type=job.doc_type,
                material_name=material_name,
                extraction_confidence=job.confidence,
                properties_count=job.properties_count,
                summary_text=all_text[:500],
                methodology=methodology,
                research_objective=research_objective,
                key_findings=key_findings,
                processing_conditions=processing_conditions,
            )

            # Upsert individual chunks — RAISES on failure (intentional)
            chunk_count = store.upsert_chunks(
                doc_id=doc_id,
                filename=job.filename,
                doc_type=job.doc_type,
                material_name=material_name,
                full_text=all_text,
            )
            print(f"[WORKER] Stored {chunk_count} chunks for {job.filename}")

            job.doc_id = doc_id
            job.qdrant_point_id = doc_id

            # Upsert individual property vectors
            for prop in properties:
                if prop.get("value") is not None:
                    try:
                        store.upsert_property(
                            doc_id=doc_id,
                            filename=job.filename,
                            material_name=material_name,
                            property_name=prop.get("property_name", ""),
                            value=prop.get("value"),
                            unit=prop.get("unit", ""),
                            confidence=prop.get("confidence", 0.5),
                            context=prop.get("context", ""),
                        )
                    except Exception as prop_e:
                        logger.warning(f"Property upsert failed: {prop_e}")

            # Auto-extract knowledge graph edges
            try:
                from knowledge_graph import get_knowledge_graph
                kg = get_knowledge_graph()
                edge_count = kg.auto_extract_edges(material_name, properties)
                print(f"[WORKER] Extracted {edge_count} knowledge graph edges for {material_name}")
            except Exception as kg_e:
                logger.warning(f"KG edge extraction failed (non-fatal): {kg_e}")

            # Check if cancelled while we were processing
            fresh = self.get_job(job.job_id)
            if fresh and fresh.status == JobStatus.CANCELLED:
                print(f"[WORKER] {job.filename} was cancelled — discarding results")
                return job

            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.current_step = "Completed"
            job.completed_at = datetime.now().isoformat()
            self.update_job(job)

            print(f"[WORKER] Completed {job.filename} — material: '{material_name}', {chunk_count} chunks, {job.properties_count} properties")

            try:
                os.remove(job.file_path)
            except Exception:
                pass

        except Exception as e:
            job.retry_count += 1
            job.error_message = str(e)
            logger.error(f"[WORKER] Error processing {job.filename}: {e}")

            if job.retry_count < job.max_retries:
                job.status = JobStatus.QUEUED
                job.current_step = f"Retry {job.retry_count}/{job.max_retries}"
                self.queue_job(job)
            else:
                job.status = JobStatus.FAILED
                job.current_step = "Failed"
                job.completed_at = datetime.now().isoformat()
                self.update_job(job)

        return job

    async def worker_loop(self):
        self._running = True
        print("[WORKER] Background worker started")

        while self._running:
            job = self.get_next_job()
            if job:
                self.active_jobs[job.job_id] = job
                await self.process_job(job)
            else:
                await asyncio.sleep(1)

        print("[WORKER] Background worker stopped")

    def recover_queued_jobs(self) -> int:
        """On startup: reload any jobs that were queued/running when the backend last stopped."""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            results, _ = self._qdrant_client.scroll(
                collection_name="job_status",
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="status",
                        match=MatchAny(any=["queued", "running"]),
                    )]
                ),
                limit=200,
                with_vectors=False,
            )
            recovered = 0
            for point in results:
                job = self._job_from_payload(point.payload)
                if not job:
                    continue
                # Only recover if the file still exists
                if not Path(job.file_path).exists():
                    job.status = JobStatus.FAILED
                    job.error_message = "File missing after restart"
                    job.completed_at = datetime.now().isoformat()
                    self._save_job(job)
                    continue
                # Reset running → queued so it starts fresh
                job.status = JobStatus.QUEUED
                job.current_step = ""
                job.progress = 0.0
                job.started_at = ""
                self._save_job(job)
                self.queue_job(job)
                recovered += 1
            if recovered:
                print(f"[WORKER] Recovered {recovered} queued job(s) from Qdrant")
            return recovered
        except Exception as e:
            logger.warning(f"Job recovery failed: {e}")
            return 0

    def start_worker(self):
        if self.worker_task is None or self.worker_task.done():
            # Disabled auto-recovery to prevent re-processing old files
            # self.recover_queued_jobs()
            self.worker_task = asyncio.create_task(self.worker_loop())

    def stop_worker(self):
        self._running = False
        if self.worker_task:
            self.worker_task.cancel()


def get_job_queue() -> JobQueue:
    return JobQueue()
