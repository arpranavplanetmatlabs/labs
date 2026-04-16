"""
job_queue.py - Background Job Queue with Priority and Qdrant Persistence

Features:
- Priority queue (high: <1MB, medium: 1-10MB, low: >10MB)
- Persistent job storage in Qdrant
- Background worker for async processing
- SSE progress updates
"""

import asyncio
import heapq
import uuid
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from enum import Enum
import os

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from config import QDRANT_URL, DATA_DIR
from parser import extract_text
from extractor import (
    extract_from_text,
    extract_properties_list,
    extract_additional_data,
)
from db import get_connection
from qdrant_mgr import get_qdrant_manager


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    HIGH = 0  # <1MB
    MEDIUM = 1  # 1-10MB
    LOW = 2  # >10MB


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
    doc_id: Optional[int] = None
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
            "status": self.status.value
            if isinstance(self.status, Enum)
            else self.status,
            "priority": self.priority.value
            if isinstance(self.priority, Enum)
            else self.priority,
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

        self.high_priority: List[Job] = []
        self.medium_priority: List[Job] = []
        self.low_priority: List[Job] = []

        self.active_jobs: Dict[str, Job] = {}
        self.job_counter = 0

        self.qdrant = get_qdrant_manager()
        self._ensure_job_collection()

        self.worker_task: Optional[asyncio.Task] = None
        self._running = False

    def _ensure_job_collection(self):
        collections = self.qdrant.client.get_collections().collections
        collection_names = [c.name for c in collections]

        if "job_status" not in collection_names:
            # Create collection with minimal vector (we'll store data in payload only)
            self.qdrant.client.create_collection(
                collection_name="job_status",
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )
            print("Created Qdrant collection: job_status")

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

        self._save_job_to_qdrant(job)
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

        self._save_job_to_qdrant(job)
        print(
            f"[QUEUE] Queued job {job.job_id} ({job.filename}) - Priority: {job.priority.name}"
        )

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
            results = self.qdrant.client.retrieve(
                collection_name="job_status", ids=[job_id]
            )
            if results:
                return self._job_from_payload(results[0].payload)
        except:
            pass
        return None

    def get_all_jobs(self, limit: int = 100) -> List[Job]:
        try:
            results = self.qdrant.client.scroll(
                collection_name="job_status", limit=limit, with_vectors=False
            )
            jobs = []
            for point in results[0]:
                job = self._job_from_payload(point.payload)
                if job:
                    jobs.append(job)
            return sorted(jobs, key=lambda j: j.created_at, reverse=True)
        except Exception as e:
            print(f"Error getting all jobs: {e}")
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
            )
        except Exception as e:
            print(f"Error parsing job payload: {e}")
            return None

    def _save_job_to_qdrant(self, job: Job) -> None:
        try:
            payload = job.to_dict()
            payload["status"] = (
                job.status.value if isinstance(job.status, Enum) else job.status
            )
            payload["priority"] = (
                job.priority.value if isinstance(job.priority, Enum) else job.priority
            )

            self.qdrant.client.upsert(
                collection_name="job_status",
                points=[{"id": job.job_id, "vector": [0], "payload": payload}],
            )
        except Exception as e:
            print(f"Error saving job to Qdrant: {e}")

    def update_job(self, job: Job) -> None:
        self.active_jobs[job.job_id] = job
        self._save_job_to_qdrant(job)

    def cancel_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if not job:
            return False

        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            return False

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now().isoformat()
        self.update_job(job)
        return True

    async def process_job(self, job: Job) -> Job:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        self.update_job(job)

        print(f"[WORKER] Processing {job.filename}...")

        try:
            job.current_step = "Extracting text"
            self.update_job(job)

            chunks = await asyncio.to_thread(extract_text, job.file_path)
            all_text = " ".join(c.get("content", "") for c in chunks)

            job.current_step = "Detecting document type"
            self.update_job(job)

            job.current_step = "Running LLM extraction"
            self.update_job(job)

            extraction_result = await asyncio.to_thread(extract_from_text, all_text)

            job.doc_type = extraction_result.get("document_type", "paper")
            job.confidence = extraction_result.get("extraction_confidence", 0.0)

            job.current_step = "Saving to database"
            self.update_job(job)

            conn = get_connection()
            result = conn.execute(
                "INSERT INTO documents (filename, doc_type, status, extraction_status, extraction_confidence, llm_output) VALUES (?, ?, 'completed', 'completed', ?, ?) RETURNING id",
                [
                    job.filename,
                    job.doc_type,
                    job.confidence,
                    json.dumps(extraction_result),
                ],
            ).fetchone()
            job.doc_id = result[0]

            properties = extract_properties_list(extraction_result)
            job.properties_count = len(properties)

            for prop in properties:
                if prop.get("value") is not None:
                    conn.execute(
                        "INSERT INTO material_properties (doc_id, property_name, value, unit, confidence, context, extraction_method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            job.doc_id,
                            prop.get("property_name"),
                            str(prop.get("value")),
                            prop.get("unit", ""),
                            prop.get("confidence", 0.5),
                            prop.get("context", ""),
                            "llm",
                        ],
                    )

            # Populate extraction_data table
            additional_data = extract_additional_data(extraction_result)
            
            # Helper to insert extraction data
            def insert_ext_data(data_type, content, confidence=0.5):
                if content:
                    serialized_content = json.dumps(content) if isinstance(content, (list, dict)) else str(content)
                    conn.execute(
                        "INSERT INTO extraction_data (doc_id, data_type, content, confidence) VALUES (?, ?, ?, ?)",
                        [job.doc_id, data_type, serialized_content, confidence]
                    )

            insert_ext_data("key_findings", additional_data.get("key_findings"), job.confidence)
            insert_ext_data("conditions", additional_data.get("conditions"), job.confidence)
            insert_ext_data("formulations", additional_data.get("formulations"), job.confidence)
            insert_ext_data("limitations", additional_data.get("limitations"), job.confidence)
            insert_ext_data("methodology", additional_data.get("methodology"), job.confidence)
            insert_ext_data("research_objective", additional_data.get("research_objective"), job.confidence)
            insert_ext_data("future_work", additional_data.get("future_work"), job.confidence)

            conn.close()

            job.current_step = "Storing in Qdrant"
            self.update_job(job)

            additional_data = extract_additional_data(extraction_result)
            metadata = {
                "material_name": extraction_result.get("material_name", ""),
                "doc_type": job.doc_type,
                "extraction_confidence": job.confidence,
                "properties": json.dumps(
                    [
                        {
                            "property": p.get("property_name"),
                            "value": str(p.get("value")),
                            "unit": p.get("unit", ""),
                        }
                        for p in properties
                    ]
                ),
                "processing_conditions": json.dumps(
                    additional_data.get("conditions", [])
                ),
                "applications": json.dumps(additional_data.get("applications", [])),
                "key_findings": json.dumps(additional_data.get("key_findings", [])),
                "methodology": additional_data.get("methodology", ""),
                "limitations": json.dumps(additional_data.get("limitations", [])),
                "formulations": json.dumps(additional_data.get("formulations", [])),
                "job_id": job.job_id,
                "source": "background_queue",
                "processed_at": datetime.now().isoformat(),
            }

            try:
                point_id = self.qdrant.add_document(
                    filename=job.filename,
                    doc_type=job.doc_type,
                    content=all_text[:10000],
                    metadata=metadata,
                    doc_id=job.doc_id,
                )
                print(f"[WORKER] Stored {job.filename} in Qdrant (ID: {point_id})")
                # Also update job with Qdrant ID for reference
                job.qdrant_point_id = point_id
            except Exception as e:
                print(f"[WORKER] ERROR storing {job.filename} in Qdrant: {e}")
                # Don't fail the job for Qdrant storage issues - we still have DB

            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.current_step = "Completed"
            job.completed_at = datetime.now().isoformat()
            self.update_job(job)

            print(f"[WORKER] Completed {job.filename} - Confidence: {job.confidence}")

            try:
                os.remove(job.file_path)
            except:
                pass

        except Exception as e:
            job.retry_count += 1
            job.error_message = str(e)
            print(f"[WORKER] Error processing {job.filename}: {e}")

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

    def start_worker(self):
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker_loop())

    def stop_worker(self):
        self._running = False
        if self.worker_task:
            self.worker_task.cancel()


def get_job_queue() -> JobQueue:
    return JobQueue()
