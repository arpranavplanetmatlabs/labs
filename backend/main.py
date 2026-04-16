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
from db import init_db, get_connection
from parser import extract_text
from extractor import (
    extract_from_text,
    extract_properties_list,
    extract_additional_data,
)
from llm import get_client
from qdrant_mgr import get_qdrant_manager
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
    init_db()

    job_queue = get_job_queue()
    job_queue.start_worker()
    print("Background job worker started!")

    print("Planet Material Labs Backend v0.5.0 started!")


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
    conn = get_connection()
    total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    tds_count = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE doc_type = 'tds'"
    ).fetchone()[0]
    papers_count = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE doc_type = 'paper'"
    ).fetchone()[0]
    experiments_count = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    conn.close()

    qdrant_parsed = 0
    try:
        qdrant = get_qdrant_manager()
        qdrant_parsed = len(qdrant.get_all_documents(limit=1000))
    except:
        pass

    return {
        "documents": total_docs,
        "tds": tds_count,
        "papers": papers_count,
        "experiments": experiments_count,
        "qdrant_parsed": qdrant_parsed,
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
    conn = get_connection()
    docs = conn.execute("""
        SELECT id, filename, doc_type, status, extraction_status, extraction_confidence, created_at 
        FROM documents 
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()

    return [
        {
            "id": doc[0],
            "filename": doc[1],
            "doc_type": doc[2],
            "status": doc[3],
            "extraction_status": doc[4],
            "extraction_confidence": doc[5],
            "created_at": str(doc[6]),
        }
        for doc in docs
    ]


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: int):
    conn = get_connection()

    doc = conn.execute(
        "SELECT id, filename, doc_type, status, extraction_status, extraction_confidence, llm_output, created_at FROM documents WHERE id = ?",
        [doc_id],
    ).fetchone()

    if not doc:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = conn.execute(
        "SELECT id, content, page_number, chunk_type FROM chunks WHERE doc_id = ? ORDER BY page_number",
        [doc_id],
    ).fetchall()

    props = conn.execute(
        "SELECT property_name, value, unit, confidence, context, extraction_method FROM material_properties WHERE doc_id = ?",
        [doc_id],
    ).fetchall()

    extraction_data = conn.execute(
        "SELECT data_type, content, confidence FROM extraction_data WHERE doc_id = ?",
        [doc_id],
    ).fetchall()

    conn.close()

    llm_output = None
    if doc[6]:
        try:
            llm_output = json.loads(doc[6]) if isinstance(doc[6], str) else doc[6]
        except:
            llm_output = doc[6]

    additional_data = {}
    for ed in extraction_data:
        try:
            content = (
                json.loads(ed[1])
                if ed[0]
                in [
                    "key_findings",
                    "limitations",
                    "formulations",
                    "conditions",
                    "applications",
                ]
                else ed[1]
            )
        except:
            content = ed[1]
        additional_data[ed[0]] = {"content": content, "confidence": ed[2]}

    return {
        "id": doc[0],
        "filename": doc[1],
        "doc_type": doc[2],
        "status": doc[3],
        "extraction_status": doc[4],
        "extraction_confidence": doc[5],
        "created_at": str(doc[7]),
        "llm_output": llm_output,
        "chunks": [
            {"id": c[0], "content": c[1], "page": c[2], "type": c[3]} for c in chunks
        ],
        "properties": [
            {
                "property": p[0],
                "value": p[1],
                "unit": p[2],
                "confidence": p[3],
                "context": p[4],
                "method": p[5],
            }
            for p in props
        ],
        "additional_data": additional_data,
    }


@app.get("/api/documents/{doc_id}/properties")
async def get_properties(doc_id: int):
    conn = get_connection()
    props = conn.execute(
        "SELECT property_name, value, unit, confidence, context FROM material_properties WHERE doc_id = ?",
        [doc_id],
    ).fetchall()
    conn.close()

    return [
        {
            "property": p[0],
            "value": p[1],
            "unit": p[2],
            "confidence": p[3],
            "context": p[4],
        }
        for p in props
    ]


@app.get("/api/documents/{doc_id}/extraction")
async def get_extraction_data(doc_id: int):
    conn = get_connection()
    doc = conn.execute(
        "SELECT llm_output, extraction_confidence, extraction_status FROM documents WHERE id = ?",
        [doc_id],
    ).fetchone()

    data = conn.execute(
        "SELECT data_type, content, confidence FROM extraction_data WHERE doc_id = ?",
        [doc_id],
    ).fetchall()
    conn.close()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    llm_output = None
    if doc[0]:
        try:
            llm_output = json.loads(doc[0]) if isinstance(doc[0], str) else doc[0]
        except:
            llm_output = doc[0]

    extraction_data = {}
    for d in data:
        try:
            content = (
                json.loads(d[1])
                if d[0]
                in [
                    "key_findings",
                    "limitations",
                    "formulations",
                    "conditions",
                    "applications",
                ]
                else d[1]
            )
        except:
            content = d[1]
        extraction_data[d[0]] = {"content": content, "confidence": d[2]}

    return {
        "llm_output": llm_output,
        "overall_confidence": doc[1],
        "status": doc[2],
        "extraction_data": extraction_data,
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
    experiment_id: int
    results: List[Dict[str, Any]]


@app.post("/api/experiments")
async def create_experiment(exp: ExperimentCreate):
    conn = get_connection()
    result = conn.execute(
        """INSERT INTO experiments (name, material_id, material_name, description, conditions, expected_output, status)
           VALUES (?, ?, ?, ?, ?, ?, 'pending') RETURNING id""",
        [
            exp.name,
            exp.material_id,
            exp.material_name,
            exp.description,
            json.dumps(exp.conditions),
            json.dumps(exp.expected_output) if exp.expected_output else None,
        ],
    ).fetchone()
    conn.close()
    return {"experiment_id": result[0], "name": exp.name, "status": "pending"}


@app.get("/api/experiments")
async def list_experiments(limit: int = 50, status_filter: Optional[str] = None):
    conn = get_connection()
    if status_filter:
        exps = conn.execute(
            "SELECT id, name, material_name, status, confidence_score, created_at FROM experiments WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            [status_filter, limit],
        ).fetchall()
    else:
        exps = conn.execute(
            "SELECT id, name, material_name, status, confidence_score, created_at FROM experiments ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    conn.close()
    return {
        "experiments": [
            {
                "id": e[0],
                "name": e[1],
                "material_name": e[2],
                "status": e[3],
                "confidence": e[4],
                "created_at": str(e[5]),
            }
            for e in exps
        ],
        "count": len(exps),
    }


@app.get("/api/experiments/{exp_id}")
async def get_experiment(exp_id: int):
    conn = get_connection()
    exp = conn.execute(
        "SELECT id, name, material_id, material_name, description, conditions, expected_output, actual_output, status, result_analysis, confidence_score, recommendation, created_at, started_at, completed_at FROM experiments WHERE id = ?",
        [exp_id],
    ).fetchone()

    if not exp:
        conn.close()
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = conn.execute(
        "SELECT id, metric_name, expected_value, actual_value, deviation_percent, passed, test_method, notes FROM experiment_results WHERE experiment_id = ?",
        [exp_id],
    ).fetchall()
    conn.close()

    return {
        "id": exp[0],
        "name": exp[1],
        "material_id": exp[2],
        "material_name": exp[3],
        "description": exp[4],
        "conditions": json.loads(exp[5]) if exp[5] else {},
        "expected_output": json.loads(exp[6]) if exp[6] else {},
        "actual_output": json.loads(exp[7]) if exp[7] else {},
        "status": exp[8],
        "result_analysis": exp[9],
        "confidence_score": exp[10],
        "recommendation": exp[11],
        "created_at": str(exp[12]) if exp[12] else None,
        "started_at": str(exp[13]) if exp[13] else None,
        "completed_at": str(exp[14]) if exp[14] else None,
        "results": [
            {
                "id": r[0],
                "metric": r[1],
                "expected": r[2],
                "actual": r[3],
                "deviation": r[4],
                "passed": r[5],
                "method": r[6],
                "notes": r[7],
            }
            for r in results
        ],
    }


@app.put("/api/experiments/{exp_id}")
async def update_experiment(
    exp_id: int,
    actual_output: Dict[str, Any],
    result_analysis: Optional[str] = None,
    recommendation: Optional[str] = None,
):
    conn = get_connection()

    conn.execute(
        "UPDATE experiments SET actual_output = ?, result_analysis = ?, recommendation = ?, status = 'completed', completed_at = NOW() WHERE id = ?",
        [json.dumps(actual_output), result_analysis, recommendation, exp_id],
    )

    conn.close()
    return {"success": True, "message": "Experiment updated"}


@app.post("/api/experiments/{exp_id}/results")
async def add_experiment_results(exp_id: int, result_input: ExperimentResultInput):
    if result_input.experiment_id != exp_id:
        raise HTTPException(status_code=400, detail="Experiment ID mismatch")

    conn = get_connection()
    for r in result_input.results:
        deviation = None
        if r.get("expected_value") and r.get("actual_value"):
            try:
                exp_val = float(r["expected_value"])
                act_val = float(r["actual_value"])
                deviation = ((act_val - exp_val) / exp_val) * 100 if exp_val != 0 else 0
            except:
                pass

        passed = deviation is not None and abs(deviation) <= 10

        conn.execute(
            """INSERT INTO experiment_results (experiment_id, metric_name, expected_value, actual_value, deviation_percent, passed, test_method, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                exp_id,
                r.get("metric_name"),
                r.get("expected_value"),
                r.get("actual_value"),
                deviation,
                passed,
                r.get("test_method"),
                r.get("notes"),
            ],
        )
    conn.close()
    return {"success": True, "message": f"Added {len(result_input.results)} results"}


@app.delete("/api/experiments/{exp_id}")
async def delete_experiment(exp_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM experiment_results WHERE experiment_id = ?", [exp_id])
    conn.execute("DELETE FROM experiments WHERE id = ?", [exp_id])
    conn.close()
    return {"success": True, "message": "Experiment deleted"}


@app.get("/api/experiments/suggest")
async def suggest_experiments(
    material_name: Optional[str] = None, property_filters: Optional[str] = None
):
    conn = get_connection()

    suggestions = []

    if material_name:
        qdrant = get_qdrant_manager()
        search_results = qdrant.search(query=material_name, limit=5)
        suggestions.append(
            {
                "type": "similar_materials",
                "message": f"Found {len(search_results)} similar materials to {material_name}",
                "materials": [
                    {
                        "filename": r["filename"],
                        "doc_type": r["doc_type"],
                        "score": r["score"],
                    }
                    for r in search_results
                ],
            }
        )

    pending_exps = conn.execute(
        "SELECT COUNT(*) FROM experiments WHERE status = 'pending'"
    ).fetchone()[0]
    completed_exps = conn.execute(
        "SELECT COUNT(*) FROM experiments WHERE status = 'completed'"
    ).fetchone()[0]

    avg_confidence = (
        conn.execute(
            "SELECT AVG(confidence_score) FROM experiments WHERE status = 'completed' AND confidence_score IS NOT NULL"
        ).fetchone()[0]
        or 0
    )

    suggestions.append(
        {
            "type": "statistics",
            "pending_experiments": pending_exps,
            "completed_experiments": completed_exps,
            "average_confidence": round(avg_confidence * 100, 1),
        }
    )

    conn.close()
    return {"suggestions": suggestions}


@app.get("/api/materials/search")
async def search_materials(q: str, limit: int = 10):
    try:
        qdrant = get_qdrant_manager()
        results = qdrant.search(query=q, limit=limit)
        return {
            "results": [
                {
                    "id": r.get("id"),
                    "filename": r.get("filename"),
                    "doc_type": r.get("doc_type"),
                    "material_name": r.get("metadata", {}).get("material_name", ""),
                    "properties": r.get("metadata", {}).get("properties", ""),
                    "score": r.get("score"),
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

    success = clear_session(session_id)
    return {
        "success": success,
        "message": "Session cleared" if success else "Session not found",
    }


@app.post("/api/experiments/{exp_id}/predict")
async def predict_experiment_properties(exp_id: int):
    from experiment_runner import run_prediction_for_experiment

    result = run_prediction_for_experiment(exp_id)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=404, detail=result.get("error", "Prediction failed")
        )

    return result


@app.post("/api/experiments/{exp_id}/suggest")
async def suggest_experiment_next(exp_id: int, goal: Optional[str] = None):
    from experiment_runner import suggest_next_configuration, get_experiment_history
    from qdrant_mgr import get_qdrant_manager

    conn = get_connection()
    exp = conn.execute(
        "SELECT name, material_name, conditions, expected_output, actual_output FROM experiments WHERE id = ?",
        [exp_id],
    ).fetchone()
    conn.close()

    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    name, material_name, conditions_json, expected_json, actual_json = exp

    current_config = {
        "name": name,
        "material": material_name,
        "conditions": json.loads(conditions_json) if conditions_json else {},
        "expected_output": json.loads(expected_json) if expected_json else {},
    }

    results = json.loads(actual_json) if actual_json else {}

    if not goal:
        goal = f"Maximize tensile strength and elongation for {material_name or name}"

    suggestions = suggest_next_configuration(exp_id, current_config, results, goal)

    return {"experiment_id": exp_id, "suggestions": suggestions, "goal": goal}


@app.get("/api/experiments/{exp_id}/history")
async def get_experiment_history_api(exp_id: int):
    from experiment_runner import get_experiment_history

    history = get_experiment_history(exp_id)

    if not history:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return {"history": history}


@app.post("/api/experiments/{exp_id}/complete")
async def complete_experiment(exp_id: int, actual_output: Dict[str, Any]):
    from experiment_runner import calculate_composite_score

    conn = get_connection()

    # Get expected output for scoring
    exp = conn.execute(
        "SELECT expected_output FROM experiments WHERE id = ?", [exp_id]
    ).fetchone()

    if not exp:
        conn.close()
        raise HTTPException(status_code=404, detail="Experiment not found")

    expected = json.loads(exp[0]) if exp[0] else {}

    # Calculate score based on actual results
    # Simplified - would use actual predictions in real implementation
    score_result = calculate_composite_score(
        predicted_props=actual_output, expected_props=expected
    )

    conn.execute(
        """UPDATE experiments 
           SET actual_output = ?, status = 'completed', confidence_score = ?, 
               completed_at = NOW() 
           WHERE id = ?""",
        [json.dumps(actual_output), score_result["composite_score"], exp_id],
    )
    conn.close()

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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
