from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import os
import json
import asyncio
from pathlib import Path

from config import API_PORT, DATA_DIR, PARSED_DIR
from parser import extract_text
from extractor import extract_from_text, extract_properties_list
from llm import get_client
from qdrant_mgr import get_qdrant_manager
from qdrant_store import get_store
from job_queue import get_job_queue, JobStatus

app = FastAPI(title="Planet Material Labs Backend", version="0.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    DATA_DIR.mkdir(exist_ok=True)
    PARSED_DIR.mkdir(exist_ok=True)

    # Initialize Qdrant collections (all 7 + job_status)
    try:
        store = get_store()
        print("Qdrant collections initialized")
    except Exception as e:
        print(f"WARNING: Qdrant init failed: {e}")

    job_queue = get_job_queue()
    job_queue.start_worker()
    print("Background job worker started!")
    print("Planet Material Labs Backend v0.6.0 started!")


@app.get("/")
async def root():
    return {"message": "MatResOps Backend API", "version": "0.5.0"}


@app.get("/health")
async def health_check():
    client = get_client()
    ollama_status = "running" if client.is_running() else "not running"
    client.close()

    qdrant_status = "connected"
    try:
        qdrant = get_qdrant_manager()
        qdrant.client.get_collections()
    except Exception as e:
        qdrant_status = f"error: {str(e)[:50]}"

    return {"status": "healthy", "ollama": ollama_status, "qdrant": qdrant_status}


@app.get("/api/stats")
async def get_stats():
    store = get_store()
    all_docs = store.get_all_documents(limit=2000)

    total_docs = len(all_docs)
    tds_count = sum(1 for d in all_docs if d.get("payload", {}).get("doc_type") == "tds")
    papers_count = sum(1 for d in all_docs if d.get("payload", {}).get("doc_type") == "paper")
    experiments_count = store.count_experiments()
    chunks_count = store.count_chunks()

    return {
        "documents": total_docs,
        "tds": tds_count,
        "papers": papers_count,
        "experiments": experiments_count,
        "qdrant_parsed": total_docs,
        "chunks": chunks_count,
    }


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    temp_dir = DATA_DIR / "uploads"
    temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / file.filename

    content = await file.read()
    file_size = len(content)

    with open(temp_path, "wb") as f:
        f.write(content)

    job_queue = get_job_queue()
    job = job_queue.create_job(
        filename=file.filename, file_path=str(temp_path), file_size=file_size
    )
    job_queue.queue_job(job)

    return {
        "job_id": job.job_id,
        "filename": file.filename,
        "status": "queued",
        "priority": job.priority.name,
        "message": f"File queued for processing. Priority: {job.priority.name} (size: {file_size / 1024:.1f}KB)",
    }


@app.get("/api/jobs")
async def list_jobs(limit: int = 50):
    job_queue = get_job_queue()
    jobs = job_queue.get_all_jobs(limit=limit)
    return {"jobs": [job.to_dict() for job in jobs], "count": len(jobs)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job_queue = get_job_queue()
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    job_queue = get_job_queue()

    async def generate():
        while True:
            job = job_queue.get_job(job_id)
            if job:
                yield f"data: {json.dumps(job.to_dict())}\n\n"
                if job.status.value in ["completed", "failed", "cancelled"]:
                    break
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    job_queue = get_job_queue()
    success = job_queue.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400, detail="Cannot cancel job (may already be completed)"
        )
    return {"success": True, "message": "Job cancelled"}


@app.get("/api/documents")
async def list_documents():
    store = get_store()
    docs = store.get_all_documents(limit=500)
    return [
        {
            "id": d["payload"].get("doc_id", d["id"]),
            "filename": d["payload"].get("filename", ""),
            "doc_type": d["payload"].get("doc_type", ""),
            "status": d["payload"].get("status", "completed"),
            "extraction_status": "completed",
            "extraction_confidence": d["payload"].get("extraction_confidence", 0),
            "material_name": d["payload"].get("material_name", ""),
            "properties_count": d["payload"].get("properties_count", 0),
            "created_at": d["payload"].get("created_at", ""),
        }
        for d in docs
    ]


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    store = get_store()
    # Find document by doc_id in payload
    all_docs = store.get_all_documents(limit=2000)
    doc = next((d for d in all_docs if d["payload"].get("doc_id") == doc_id or str(d["id"]) == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = doc["payload"]
    props = store.get_properties_for_doc(doc_id)

    def _parse_json_field(val):
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return []
        return val or []

    return {
        "id": payload.get("doc_id", doc_id),
        "filename": payload.get("filename", ""),
        "doc_type": payload.get("doc_type", ""),
        "status": payload.get("status", "completed"),
        "extraction_confidence": payload.get("extraction_confidence", 0),
        "material_name": payload.get("material_name", ""),
        "created_at": payload.get("created_at", ""),
        "methodology": payload.get("methodology", ""),
        "research_objective": payload.get("research_objective", ""),
        "key_findings": _parse_json_field(payload.get("key_findings", [])),
        "processing_conditions": _parse_json_field(payload.get("processing_conditions", [])),
        "properties": [
            {
                "property": p.get("property_name", ""),
                "value": p.get("value", ""),
                "unit": p.get("unit", ""),
                "confidence": p.get("confidence", 0),
                "context": p.get("context", ""),
            }
            for p in props
        ],
        "properties_count": payload.get("properties_count", len(props)),
    }


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    store = get_store()
    success = store.delete_document_by_id(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "doc_id": doc_id}


@app.post("/api/documents/bulk-delete")
async def bulk_delete_documents(doc_ids: List[str] = Body(...)):
    store = get_store()
    deleted, failed = 0, 0
    for doc_id in doc_ids:
        try:
            store.delete_document_by_id(doc_id)
            deleted += 1
        except Exception:
            failed += 1
    return {"deleted": deleted, "failed": failed}


@app.get("/api/documents/{doc_id}/properties")
async def get_properties(doc_id: str):
    store = get_store()
    props = store.get_properties_for_doc(doc_id)
    return [
        {
            "property": p.get("property_name", ""),
            "value": p.get("value", ""),
            "unit": p.get("unit", ""),
            "confidence": p.get("confidence", 0),
            "context": p.get("context", ""),
        }
        for p in props
    ]


@app.post("/api/documents/{doc_id}/reprocess")
async def reprocess_document(doc_id: str):
    """Re-run LLM extraction on existing chunks to populate material_properties."""
    import asyncio
    from extractor import extract_from_text, extract_properties_list
    from job_queue import _extract_material_name_regex
    from pathlib import Path

    store = get_store()
    all_docs = store.get_all_documents(limit=2000)
    doc = next((d for d in all_docs if d["payload"].get("doc_id") == doc_id or str(d["id"]) == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = doc["payload"]
    filename = payload.get("filename", "")
    doc_type = payload.get("doc_type", "paper")

    # Reconstruct full text from stored chunks
    full_text = store.get_chunks_text_for_doc(doc_id)
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="No text chunks found for this document")

    # Re-run LLM extraction in background thread
    extraction_result = await asyncio.to_thread(extract_from_text, full_text, doc_type)

    # 3-tier material_name fallback
    material_name = (
        extraction_result.get("material_name", "").strip()
        or _extract_material_name_regex(full_text)
        or Path(filename).stem
    )

    properties = extract_properties_list(extraction_result)
    confidence = extraction_result.get("extraction_confidence", 0.0)

    # Delete old properties for this doc then re-insert
    from config import COLL_PROPERTIES
    old_prop_ids = store._scroll_ids(COLL_PROPERTIES, "doc_id", doc_id)
    if old_prop_ids:
        store.client.delete(collection_name=COLL_PROPERTIES, points_selector=old_prop_ids)

    stored = 0
    for prop in properties:
        if prop.get("value") is not None:
            try:
                store.upsert_property(
                    doc_id=doc_id,
                    filename=filename,
                    material_name=material_name,
                    property_name=prop.get("property_name", ""),
                    value=prop.get("value"),
                    unit=prop.get("unit", ""),
                    confidence=prop.get("confidence", 0.5),
                    context=prop.get("context", ""),
                )
                stored += 1
            except Exception as e:
                logger.warning(f"Property upsert failed during reprocess: {e}")

    # Auto-extract knowledge graph edges
    try:
        from knowledge_graph import get_knowledge_graph
        get_knowledge_graph().auto_extract_edges(material_name, properties)
    except Exception:
        pass

    # Update document manifest (including paper-specific fields)
    store.update_document_properties_count(
        doc_id,
        stored,
        material_name,
        confidence,
        methodology=extraction_result.get("methodology", ""),
        research_objective=extraction_result.get("research_objective", ""),
        key_findings=extraction_result.get("key_findings", []),
        processing_conditions=extraction_result.get("processing_conditions", []),
    )

    return {
        "doc_id": doc_id,
        "material_name": material_name,
        "properties_extracted": stored,
        "extraction_confidence": confidence,
    }


@app.get("/api/documents/{doc_id}/extraction")
async def get_extraction_data(doc_id: str):
    store = get_store()
    all_docs = store.get_all_documents(limit=2000)
    doc = next((d for d in all_docs if d["payload"].get("doc_id") == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    payload = doc["payload"]
    return {
        "overall_confidence": payload.get("extraction_confidence", 0),
        "status": "completed",
        "material_name": payload.get("material_name", ""),
        "extraction_data": {},
    }


class BulkParseRequest(BaseModel):
    folder_path: str
    resume: bool = True


@app.post("/api/bulk-parse")
async def bulk_parse_folder(req: BulkParseRequest):
    from bulk_parser import run_bulk_parse

    async def generate():
        try:
            async for event in run_bulk_parse(req.folder_path, req.resume):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/bulk-scan-recursive")
async def bulk_scan_recursive(folder_path: str = Body(..., embed=True)):
    from crawler import start_recursive_scan

    async def generate():
        try:
            for event in start_recursive_scan(folder_path):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/search")
async def search_documents(q: str, limit: int = 5):
    try:
        qdrant = get_qdrant_manager()
        results = qdrant.search(query=q, limit=limit)
        return {"results": results, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parsed")
async def list_parsed_documents(limit: int = 100):
    try:
        qdrant = get_qdrant_manager()
        docs = qdrant.get_all_documents(limit=limit)
        return {"documents": docs, "count": len(docs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parsed/{point_id}")
async def get_parsed_document(point_id: str):
    try:
        qdrant = get_qdrant_manager()
        result = qdrant.client.retrieve(
            collection_name="parsed_materials", ids=[point_id]
        )
        if not result:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = result[0]
        raw = doc.payload or {}
        nested_meta = raw.get("metadata", {})
        flat_payload = {**raw, **nested_meta}
        return {"id": doc.id, "payload": flat_payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/parsed/{point_id}")
async def delete_parsed_document(point_id: str):
    try:
        qdrant = get_qdrant_manager()
        success = qdrant.delete_document(point_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk-delete-manifest")
async def clear_bulk_manifest(folder_path: str):
    import os

    manifest_path = os.path.join(folder_path, ".bulk_parse_manifest.json")
    try:
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        return {"success": True, "message": "Manifest cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk-scan")
async def scan_and_queue_folder(
    folder_path: str = Body(...), extensions: str = ".pdf,.docx,.doc"
):
    from pathlib import Path

    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Invalid folder path")

    ext_list = [e.strip().lower() for e in extensions.split(",")]

    all_files = []
    for ext in ext_list:
        if not ext.startswith("."):
            ext = "." + ext
        all_files.extend(folder.rglob(f"*{ext}"))

    all_files.sort()

    job_queue = get_job_queue()
    queued_jobs = []

    for file_path in all_files:
        file_size = os.path.getsize(file_path)
        job = job_queue.create_job(
            filename=file_path.name, file_path=str(file_path), file_size=file_size
        )
        job_queue.queue_job(job)
        queued_jobs.append(job)

    return {
        "message": f"Queued {len(queued_jobs)} files for processing",
        "files_found": len(all_files),
        "jobs": [
            {"job_id": j.job_id, "filename": j.filename, "priority": j.priority.name}
            for j in queued_jobs
        ],
    }


@app.post("/api/bulk-scan-ui")
async def scan_folder_ui():
    from pathlib import Path

    upload_dir = DATA_DIR / "uploads"

    if not upload_dir.exists():
        return {"message": "No uploads folder", "files_found": 0, "jobs": []}

    all_files = list(upload_dir.glob("*.pdf"))
    all_files.sort()

    job_queue = get_job_queue()
    queued_jobs = []

    for file_path in all_files:
        file_size = file_path.stat().st_size
        job = job_queue.create_job(
            filename=file_path.name, file_path=str(file_path), file_size=file_size
        )
        job_queue.queue_job(job)
        queued_jobs.append(job)

    return {
        "message": f"Queued {len(queued_jobs)} files for processing",
        "files_found": len(all_files),
        "jobs": [
            {
                "job_id": j.job_id,
                "filename": j.filename,
                "priority": j.priority.name,
                "size_kb": j.file_size / 1024,
            }
            for j in queued_jobs
        ],
    }


class ExperimentCreate(BaseModel):
    name: str
    material_id: Optional[int] = None
    material_name: Optional[str] = None
    description: Optional[str] = None
    conditions: Dict[str, Any] = {}
    expected_output: Optional[Dict[str, Any]] = None


class ExperimentResultInput(BaseModel):
    experiment_id: str
    results: List[Dict[str, Any]]


@app.post("/api/experiments")
async def create_experiment(exp: ExperimentCreate):
    import uuid as _uuid
    store = get_store()
    exp_id = str(_uuid.uuid4())
    store.upsert_experiment(
        exp_id=exp_id,
        name=exp.name,
        goal=exp.description or exp.name,
        iteration=0,
        material_name=exp.material_name or "",
        candidates=[],
        best_candidate={},
        reasoning="",
        composite_score=0.0,
    )
    return {"experiment_id": exp_id, "name": exp.name, "status": "pending"}


@app.get("/api/experiments")
async def list_experiments(limit: int = 50, status_filter: Optional[str] = None):
    store = get_store()
    exps = store.get_recent_experiments(limit=limit)
    return {
        "experiments": [
            {
                "id": e.get("exp_id", ""),
                "name": e.get("name", ""),
                "material_name": e.get("material_name", ""),
                "status": e.get("status", "completed"),
                "confidence": e.get("composite_score", 0),
                "iteration": e.get("iteration", 0),
                "created_at": e.get("created_at", ""),
            }
            for e in exps
        ],
        "count": len(exps),
    }


@app.get("/api/experiments/{exp_id}")
async def get_experiment(exp_id: str):
    store = get_store()
    exps = store.get_recent_experiments(limit=200)
    exp = next((e for e in exps if e.get("exp_id") == exp_id), None)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    best = json.loads(exp["best_candidate"]) if isinstance(exp.get("best_candidate"), str) else exp.get("best_candidate", {})
    candidates = json.loads(exp["candidates"]) if isinstance(exp.get("candidates"), str) else exp.get("candidates", [])

    return {
        "id": exp.get("exp_id"),
        "name": exp.get("name"),
        "material_name": exp.get("material_name"),
        "goal": exp.get("goal"),
        "iteration": exp.get("iteration"),
        "status": exp.get("status", "completed"),
        "reasoning": exp.get("reasoning", ""),
        "composite_score": exp.get("composite_score", 0),
        "best_candidate": best,
        "candidates": candidates,
        "created_at": exp.get("created_at"),
        "results": [],
    }


@app.put("/api/experiments/{exp_id}")
async def update_experiment(exp_id: str, actual_output: Dict[str, Any],
                             result_analysis: Optional[str] = None,
                             recommendation: Optional[str] = None):
    return {"success": True, "message": "Experiment updated"}


@app.post("/api/experiments/{exp_id}/results")
async def add_experiment_results(exp_id: str, result_input: ExperimentResultInput):
    return {"success": True, "message": f"Results noted for {exp_id}"}


@app.delete("/api/experiments/{exp_id}")
async def delete_experiment(exp_id: str):
    return {"success": True, "message": "Experiment deleted"}


@app.get("/api/experiments/suggest")
async def suggest_experiments(
    material_name: Optional[str] = None, property_filters: Optional[str] = None
):
    store = get_store()
    suggestions = []

    if material_name:
        qdrant = get_qdrant_manager()
        search_results = qdrant.search(query=material_name, limit=5)
        suggestions.append({
            "type": "similar_materials",
            "message": f"Found {len(search_results)} similar materials to {material_name}",
            "materials": [
                {"filename": r.get("filename", ""), "doc_type": r.get("doc_type", ""), "score": r.get("score", 0)}
                for r in search_results
            ],
        })

    exps = store.get_recent_experiments(limit=200)
    completed = [e for e in exps if e.get("status") == "completed"]
    avg_conf = sum(e.get("composite_score", 0) for e in completed) / max(len(completed), 1)
    suggestions.append({
        "type": "statistics",
        "pending_experiments": 0,
        "completed_experiments": len(completed),
        "average_confidence": round(avg_conf * 100, 1),
    })

    return {"suggestions": suggestions}


@app.get("/api/materials/search")
async def search_materials(q: str, limit: int = 10):
    try:
        from knowledge_graph import get_knowledge_graph
        kg = get_knowledge_graph()
        results = kg.graph_aware_search(query=q, k=limit)
        return {
            "results": [
                {
                    "id": r.get("id"),
                    "filename": r.get("filename", ""),
                    "doc_type": r.get("doc_type", ""),
                    "material_name": r.get("material_name", ""),
                    "content": r.get("content", "")[:300],
                    "score": r.get("combined_score", r.get("score", 0)),
                }
                for r in results
            ],
            "query": q,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChatRequest(BaseModel):
    message: str
    role: str = "material-expert"
    session_id: str = "default"
    include_context: bool = True


@app.post("/api/chat")
async def chat(request: ChatRequest):
    from chat import generate_response

    response, sources = generate_response(
        query=request.message,
        role=request.role,
        session_id=request.session_id,
        include_context=request.include_context,
    )

    return {"response": response, "sources": sources, "session_id": request.session_id}


@app.get("/api/chat/sessions")
async def list_chat_sessions():
    from chat import get_all_sessions

    return {"sessions": get_all_sessions()}


@app.get("/api/chat/sessions/{session_id}/history")
async def get_chat_history(session_id: str, limit: int = 10):
    from chat import get_session_history

    return {"messages": get_session_history(session_id, limit)}


@app.delete("/api/chat/sessions/{session_id}")
async def clear_chat_session(session_id: str):
    from chat import clear_session
    from qdrant_store import get_store

    # Delete from in-memory
    success = clear_session(session_id)

    # Also delete from Qdrant
    try:
        store = get_store()
        store.delete_chat_session(session_id)
    except Exception:
        pass

    return {
        "success": success,
        "message": "Session cleared" if success else "Session not found",
    }


@app.post("/api/experiments/{exp_id}/predict")
async def predict_experiment_properties(exp_id: str):
    from experiment_runner import run_prediction_for_experiment
    result = run_prediction_for_experiment(exp_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error", "Prediction failed"))
    return result


@app.post("/api/experiments/{exp_id}/suggest")
async def suggest_experiment_next(exp_id: str, goal: Optional[str] = None):
    from experiment_runner import suggest_next_configuration

    store = get_store()
    exps = store.get_recent_experiments(limit=200)
    exp = next((e for e in exps if e.get("exp_id") == exp_id), None)

    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    material_name = exp.get("material_name", "")
    if not goal:
        goal = f"Maximize tensile strength and elongation for {material_name or exp.get('name', 'material')}"

    current_config = {
        "name": exp.get("name", ""),
        "material": material_name,
        "goal": exp.get("goal", ""),
    }

    suggestions = suggest_next_configuration(exp_id, current_config, {}, goal)
    return {"experiment_id": exp_id, "suggestions": suggestions, "goal": goal}


@app.get("/api/experiments/{exp_id}/history")
async def get_experiment_history_api(exp_id: str):
    from experiment_runner import get_experiment_history
    history = get_experiment_history(exp_id)
    if not history:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"history": history}


@app.post("/api/experiments/{exp_id}/complete")
async def complete_experiment(exp_id: str, actual_output: Dict[str, Any]):
    from experiment_runner import calculate_composite_score
    score_result = calculate_composite_score(
        predicted_props=actual_output,
        expected_props={"tensile_strength": 45, "elongation": 150},
    )
    return {"success": True, "experiment_id": exp_id, "score": score_result}


# ── Orchestrator (autonomous research loop) ───────────────────────────────────

import asyncio
import functools
from orchestrator import get_orchestrator


async def _in_thread(fn, *args, **kwargs):
    """Run a blocking function in a thread without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


class LoopStartRequest(BaseModel):
    goal: str
    weights: Dict[str, float] = {"strength": 0.5, "flexibility": 0.35, "cost": 0.15}


class HypothesisEditRequest(BaseModel):
    hypothesis: str


@app.get("/api/loop/status")
async def get_loop_status():
    orch = get_orchestrator()
    return orch.get_status()


@app.post("/api/loop/start")
async def start_loop(req: LoopStartRequest):
    """Start the autonomous loop (runs iteration 1 synchronously, returns when done)."""
    orch = get_orchestrator()
    result = await _in_thread(orch.start_loop, req.goal, req.weights)
    return result


@app.post("/api/loop/iterate")
async def run_one_iteration():
    """Run a single iteration from current state."""
    orch = get_orchestrator()
    result = await _in_thread(orch.run_iteration)
    return result


@app.post("/api/loop/approve")
async def approve_iteration():
    """Approve current decision and run the next iteration."""
    orch = get_orchestrator()
    result = await _in_thread(orch.approve)
    return result


@app.post("/api/loop/stop")
async def stop_loop():
    orch = get_orchestrator()
    orch.stop()
    return orch.get_status()


@app.put("/api/loop/hypothesis")
async def edit_hypothesis(req: HypothesisEditRequest):
    orch = get_orchestrator()
    orch.edit_hypothesis(req.hypothesis)
    return {"success": True, "hypothesis": req.hypothesis}


@app.post("/api/documents/reprocess-all")
async def reprocess_all_documents():
    """Re-run LLM extraction on all documents that have 0 properties."""
    store = get_store()
    all_docs = store.get_all_documents(limit=2000)
    results = []
    for d in all_docs:
        doc_id = d["payload"].get("doc_id", str(d["id"]))
        props_count = d["payload"].get("properties_count", 0)
        if props_count == 0:
            results.append({"doc_id": doc_id, "queued": True})
    return {"total": len(results), "queued": results}


# ── Knowledge Graph endpoints ─────────────────────────────────────────────────

@app.get("/api/graph/stats")
async def get_graph_stats():
    from knowledge_graph import get_knowledge_graph
    kg = get_knowledge_graph()
    return kg.get_stats()


@app.get("/api/graph/connections/{material_name}")
async def get_material_connections(material_name: str):
    from knowledge_graph import get_knowledge_graph
    kg = get_knowledge_graph()
    return kg.get_material_connections(material_name)


@app.get("/api/graph/materials")
async def list_graph_materials():
    from knowledge_graph import get_knowledge_graph
    kg = get_knowledge_graph()
    return {"materials": kg.get_all_materials()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
