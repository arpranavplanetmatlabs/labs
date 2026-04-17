# Planet Material Labs — AI Research Platform
## Project Document v1.0
### April 2026 | Internal — Confidential

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Vision & Strategic Goal](#3-vision--strategic-goal)
4. [What Has Been Built](#4-what-has-been-built)
5. [System Architecture](#5-system-architecture)
6. [Technology Stack & Justification](#6-technology-stack--justification)
7. [Backend — Module-by-Module Breakdown](#7-backend--module-by-module-breakdown)
8. [Frontend — Component-by-Component Breakdown](#8-frontend--component-by-component-breakdown)
9. [Data Flows](#9-data-flows)
10. [The Autonomous Research Loop](#10-the-autonomous-research-loop)
11. [Knowledge Base & Retrieval System](#11-knowledge-base--retrieval-system)
12. [API Surface](#12-api-surface)
13. [Current Limitations & Honest Assessment](#13-current-limitations--honest-assessment)
14. [Strategic Roadmap](#14-strategic-roadmap)
15. [Infrastructure Path to Company-Wide Deployment](#15-infrastructure-path-to-company-wide-deployment)

---

# 1. Executive Summary

Planet Material Labs is building an **AI-powered materials research platform** that turns a growing corpus of technical documents — datasheets, research papers, experiment records — into a queryable, reasoning-capable intelligence layer for materials scientists and designers.

The platform combines three capabilities that do not exist together in any commercial tool:

1. **Automated structured extraction** — PDFs are parsed and all material properties (values, units, test standards, confidence scores) are extracted automatically using a local LLM and stored in a semantic vector database. No manual data entry.

2. **Autonomous experiment loop** — Given a research goal and optimization targets, the system retrieves the most relevant knowledge from the indexed corpus, proposes experiment configurations grounded in that knowledge, scores them against the goal, and presents them for human approval. The researcher approves or edits, and the loop iterates.

3. **RAG-powered expert chat** — Researchers can ask natural-language questions across the entire indexed library and receive expert-level answers grounded in their own documents, with source citations. Not generic internet knowledge.

**Why this architecture (RAG, not fine-tuning)?**
The system uses Retrieval-Augmented Generation rather than a fine-tuned model. This is a deliberate choice: RAG scales with the corpus — every document uploaded immediately improves answer quality. A fine-tuned model's knowledge is frozen at training time and requires expensive retraining to update. For a living research database that grows daily, RAG is the correct architecture. Fine-tuning becomes relevant in a later phase once the corpus has accumulated enough verified extractions to serve as training data.

**Current state:** A fully functional v1 platform is running locally on a single workstation. The ingestion pipeline, chat system, experiment management, knowledge graph, and complete UI are operational. The system has been validated on real PDF documents.

**Immediate next stage (2 weeks):** Domain intelligence upgrade — making the extractor and loop understand advanced materials science vocabulary — followed by flexible experiment schema and a fully grounded orchestrator with no placeholder logic.

---

# 2. Problem Statement

Materials researchers today face three compounding inefficiencies:

**Problem 1 — Buried knowledge.** A team of researchers may collectively have 2,000+ technical datasheets and 500+ papers. Querying this corpus for a specific property — "which of our indexed materials has tensile strength above 80 MPa and density below 1.3 g/cm³?" — requires manual search or hoping someone remembers the right document. There is no queryable index.

**Problem 2 — Disconnected experiment planning.** Researchers plan new experiments based on personal memory, spreadsheets, or informal discussion. There is no system that says "given what you already know from your document library, here is the most logical next configuration to try, and here is why — citing which papers support it."

**Problem 3 — Redundant literature review.** Every new project starts with the same literature review cycle — search, download, read, tabulate properties, discard duplicates. This takes weeks and the output (a spreadsheet) is not queryable by future researchers. The work disappears into a file nobody opens again.

The platform directly addresses all three. Every uploaded document immediately becomes part of a searchable, reasoning-capable knowledge graph. Every experiment is logged and feeds the next hypothesis. Literature review happens once; the output persists and compounds forever.

---

# 3. Vision & Strategic Goal

**Long-term vision:** A company-wide AI research assistant where every materials scientist, designer, and engineer has instant access to the collective institutional knowledge — every property ever measured, every paper ever read, every experiment ever run — and an AI that can reason over it to accelerate new material discovery.

**Guiding principle:** The system gets smarter every time someone uploads a document. The value compounds. After 6 months of use, a researcher joining the company has access to years of institutional knowledge on day one.

**What it is not:** A search engine. A document viewer. A chatbot with internet access. This is a closed-loop research intelligence system operating entirely on internal, proprietary data.

**Why fully local?**
Proprietary materials data — formulations, test results, unpublished research — must not leave the organisation. Cloud LLM APIs are not acceptable for this use case. The local stack achieves comparable quality to cloud APIs for structured extraction tasks while guaranteeing complete data sovereignty. No API cost. No data leakage.

---

# 4. What Has Been Built

The following capabilities are fully operational as of v1.0:

### 4.1 Document Ingestion Pipeline
**What it does:** Takes a PDF, extracts all text, identifies whether it is a Technical Data Sheet or a Research Paper, runs the LLM to pull out every numerical property with its unit and test standard, and stores everything in the vector database. The user just uploads a file — everything else is automatic.

- Upload individual PDFs or scan entire folders recursively
- Automatic document type detection (TDS vs. Research Paper) using keyword frequency scoring
- LLM-powered property extraction — all numerical properties with values, units, test standards, and confidence scores (0–1)
- For research papers: methodology, research objective, key findings, and processing conditions extracted separately
- SHA-256 deduplication — the same file can never be indexed twice regardless of filename
- Background priority queue (HIGH / MEDIUM / LOW by file size) — uploads never block the UI
- Job status streaming via Server-Sent Events — live progress visible in the browser without polling

### 4.2 Semantic Knowledge Base
**What it does:** Stores all document content as mathematical vectors so that semantically similar content can be found even when the exact words don't match. "Tensile modulus" and "Young's modulus" will retrieve the same results.

- All document text split into 2000-character chunks with 200-character overlap
- Each chunk embedded as a 768-dimensional vector using `nomic-embed-text`
- 8 purpose-built Qdrant collections storing structured data at different granularities
- Full-text reconstruction from stored chunks available for reprocessing

### 4.3 Knowledge Graph
**What it does:** Builds a network of relationships between materials, properties, and documents. When you search for a material, it also surfaces related materials, connected properties, and source documents — even if they don't share the same words. Finds things that pure keyword or vector search misses.

- NetworkX directed graph built automatically from indexed documents
- Nodes: materials, properties, documents, conditions
- Edges: HAS_PROPERTY, IMPROVES, DEGRADES, SIMILAR_TO, MEASURED_BY, CONTAINS
- Re-ranking formula: `0.6 × vector_score + 0.3 × PageRank + 0.1 × connectivity`
- 2-hop neighbourhood expansion for richer context retrieval
- Auto-rebuilt every 5 minutes from live Qdrant data

### 4.4 Autonomous Research Loop
**What it does:** Given a research goal ("maximise EMI shielding in a lightweight composite"), the loop retrieves the most relevant knowledge from the indexed corpus, proposes 3 experiment candidates with predicted scores, generates reasoning for why each candidate is worth trying, and waits for the researcher to approve the best one before moving to the next iteration.

- State machine: idle → running → awaiting_approval → loop/stop
- 5-step pipeline per iteration: Retrieve → Generate → Evaluate → Decide → Approve
- Human-in-the-loop approval gate before every next iteration
- User-configurable optimization weights (e.g. strength 60% / flexibility 30% / cost 10%)
- Full iteration history preserved in Qdrant — the loop can see what has been tried
- Hypothesis text editable before approval

### 4.5 RAG Chat System
**What it does:** Answers natural-language questions about the indexed document library. The answer is grounded only in the documents you have uploaded — it cites which files it drew from. Three expert roles shift the reasoning style depending on what you need.

- Three expert roles: Material Expert (technical values and standards), Technical Reviewer (QA and compliance gaps), Literature Researcher (synthesis and research gaps)
- Session memory (last 4 turns) persisted to Qdrant — conversation context survives browser refresh
- SSE token streaming — responses appear word-by-word in the browser
- Source attribution — every response lists the documents it drew from

### 4.6 Experiment Management
**What it does:** A full experiment tracking system. Create an experiment, set expected outputs, run it in the lab, come back and log the actual results. The AI can predict properties for any proposed configuration and suggest what to try next based on the results.

- Create, track, and manage experiments with full CRUD
- Log real test results post-experiment
- AI property prediction for any proposed configuration (pulls from indexed property data)
- Next-configuration suggestions after experiment completion
- 3-column kanban board (Queued / Running / Completed) for visual status tracking

### 4.7 Full React UI
**What it does:** The browser interface for everything. Six views, each purpose-built for a different workflow. Designed to feel fast and professional.

- 6 navigation views: Research, Papers, Experiments, Results, Decisions, Chat
- Electric Indigo glassmorphism design system
- Collapsible sidebar with persistent state
- Smooth page transition animations
- Bulk document delete with checkbox selection
- Live system status indicators (Ollama, Qdrant, Engine)

---

# 5. System Architecture

## 5.1 High-Level Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     PLANET MATERIAL LABS PLATFORM                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────────┐ ║
║  │                     REACT FRONTEND  (Port 5173)                      │ ║
║  │                                                                       │ ║
║  │   Research    Papers    Experiments    Results    Decisions    Chat   │ ║
║  │      │           │           │            │           │          │   │ ║
║  │   GoalPanel  PapersView  Experiments  ResultsPanel DecisionPanel│   │ ║
║  │   DecisionP  DocDetails  Kanban Board  Recharts    Loop Ctrl   Chat  │ ║
║  │   KnowPanel  BulkUpload  ExpModals    Comparison  HypothEdit  Panel  │ ║
║  └──────────────────────────────┬──────────────────────────────────────┘ ║
║                                 │  REST / SSE  (HTTP)                    ║
║  ┌──────────────────────────────▼──────────────────────────────────────┐ ║
║  │                    FASTAPI BACKEND  (Port 8000)                       │ ║
║  │                                                                       │ ║
║  │  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │ ║
║  │  │  INGESTION     │  │  RESEARCH LOOP  │  │  CHAT & SEARCH      │   │ ║
║  │  │                │  │                 │  │                     │   │ ║
║  │  │  job_queue.py  │  │ orchestrator.py │  │  chat.py            │   │ ║
║  │  │  parser.py     │  │ experiment_     │  │  knowledge_graph.py │   │ ║
║  │  │  extractor.py  │  │ runner.py       │  │  qdrant_mgr.py      │   │ ║
║  │  └───────┬────────┘  └────────┬────────┘  └──────────┬──────────┘   │ ║
║  │          │                    │                       │              │ ║
║  │          └────────────────────┼───────────────────────┘              │ ║
║  │                               │                                      │ ║
║  │                    ┌──────────▼──────────┐                          │ ║
║  │                    │   qdrant_store.py    │                          │ ║
║  │                    │  (Storage Layer)     │                          │ ║
║  │                    └──────────┬───────────┘                          │ ║
║  └───────────────────────────────┼──────────────────────────────────────┘ ║
║                                  │                                        ║
║  ┌───────────────────────────────▼──────────────────────────────────────┐ ║
║  │                     QDRANT  (Port 6333 — Local On-Disk)               │ ║
║  │                                                                        │ ║
║  │  documents │ doc_chunks │ material_properties │ experiments            │ ║
║  │  knowledge_edges │ scanned_folders │ job_status │ chat_sessions        │ ║
║  └───────────────────────────────┬──────────────────────────────────────┘ ║
║                                  │                                        ║
║  ┌───────────────────────────────▼──────────────────────────────────────┐ ║
║  │                     OLLAMA  (Port 11434 — CUDA)                       │ ║
║  │                                                                        │ ║
║  │   qwen2.5:3b-instruct-q4_K_S    (LLM — extraction, chat, reasoning)  │ ║
║  │   nomic-embed-text               (Embeddings — 768-dim vectors)       │ ║
║  └──────────────────────────────────────────────────────────────────────┘ ║
╚══════════════════════════════════════════════════════════════════════════╝
```

## 5.2 Qdrant Collections Schema

Each collection serves a distinct purpose. The schema is intentionally flat — all data stored as top-level payload fields, no nested metadata.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     QDRANT — 8 COLLECTIONS                               │
├──────────────────────┬──────────────┬───────────────────────────────────┤
│ Collection           │ Vector Dim   │ Purpose                           │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ documents            │ 768          │ 1 entry per file — manifest        │
│                      │              │ filename, hash, type, status,      │
│                      │              │ methodology, key_findings,         │
│                      │              │ research_objective, confidence     │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ doc_chunks           │ 768          │ Primary search target              │
│                      │              │ 2000-char chunks, 200 overlap      │
│                      │              │ Cosine similarity search           │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ material_properties  │ 768          │ One row per extracted property     │
│                      │              │ name, value, unit, confidence,     │
│                      │              │ context (test standard)            │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ experiments          │ 768          │ Loop iterations + manual exps      │
│                      │              │ candidates, scores, reasoning,     │
│                      │              │ actual_output, results             │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ knowledge_edges      │ 768          │ Graph edges (source, target,       │
│                      │              │ edge_type, weight)                 │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ scanned_folders      │ 1 (dummy)    │ Folder registry for dedup          │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ job_status           │ 1 (dummy)    │ Ingestion job tracking             │
│                      │              │ Survives backend restarts          │
├──────────────────────┼──────────────┼───────────────────────────────────┤
│ chat_sessions        │ 1 (dummy)    │ Conversation history               │
│                      │              │ Persisted across browser sessions  │
└──────────────────────┴──────────────┴───────────────────────────────────┘
```

## 5.3 The Compound Knowledge Effect

This is the core reason the system becomes more valuable over time, not less:

```
 DAY 1                  MONTH 1               MONTH 6
 ─────                  ───────               ───────

 Upload 10 TDS          Upload 200 docs       Upload 1000+ docs
      │                      │                     │
      ▼                      ▼                     ▼
 ~150 properties        ~3,000 properties     ~15,000+ properties
 ~20 doc chunks         ~400 doc chunks       ~2,000+ doc chunks
 Basic chat works       Chat answers well     Chat cites 8 sources
 Loop guesses           Loop extrapolates     Loop predicts with
                        from your data        high confidence
```

Every document uploaded permanently improves the quality of every future answer, prediction, and experiment suggestion. Literature review happens once; the output persists forever.

---

# 6. Technology Stack & Justification

| Component | Technology | Why This Choice |
|---|---|---|
| **LLM** | Qwen2.5:3b (Q4_K_S) via Ollama | Fits entirely in 4GB VRAM → full GPU, ~40 tok/s. Strict JSON output mode. No API cost. No data sent externally. |
| **Embeddings** | nomic-embed-text (768-dim) | State-of-the-art open embedding model. 768-dim balances quality vs. storage. Runs locally. ~274MB VRAM. |
| **Vector DB** | Qdrant | Purpose-built for production vector search. Handles millions of points. On-disk persistence. Supports payload filtering — critical for structured property queries. |
| **Backend** | FastAPI + Python | Async SSE streaming out of the box. Pydantic validation. Automatic OpenAPI docs at `/docs`. |
| **Knowledge Graph** | NetworkX | In-memory graph operations (2-hop traversal, PageRank) without a separate graph DB. Rebuilt from Qdrant on 5-min TTL. |
| **Frontend** | React 18 + Vite | Fast HMR dev cycle. No framework overhead. |
| **Desktop Shell** | Tauri (dormant) | Future: package as a zero-install `.exe` for lab distribution. Already scaffolded. |
| **PDF Parsing** | pdfplumber + PyPDF2 | Two-layer fallback. pdfplumber handles complex table layouts. PyPDF2 handles simple text extraction. |

**GPU performance note:**
The RTX 3050 has 4GB VRAM. The 3b model at Q4_K_S quantisation requires ~1.9GB — it fits entirely in VRAM. LLM inference is memory-bandwidth bound, not compute-bound: the GPU draws ~20W at 40 tok/s and this is normal and correct. The performance ceiling is the VRAM bus speed (192 GB/s), not CUDA core utilisation. Switching to a larger model (14b) would drop inference to ~4-8 tok/s due to partial CPU offload and is not the right move on this hardware.

---

# 7. Backend — Module-by-Module Breakdown

## 7.1 `main.py` — API Surface

**What it does:** The FastAPI application entry point. Defines all HTTP and SSE routes. On startup: initialises all 8 Qdrant collections (creates them if missing), starts the job queue worker as a background daemon thread, and warms up the knowledge graph.

Domain groups:
- **Documents:** Upload, list, fetch, delete (single + bulk), reprocess
- **Jobs:** Status polling, SSE progress stream, cancel
- **Bulk operations:** Folder scan (recursive, SSE stream), bulk parse, reprocess-all
- **Experiments:** Full CRUD + predict + suggest + complete + history
- **Research Loop:** Start, iterate, approve, stop, edit hypothesis
- **Chat:** Send message (SSE), session management
- **Knowledge Graph:** Stats, material connections, material list
- **Search:** Semantic search, graph-aware search

51 endpoints total. Auto-documented at `http://localhost:8000/docs`.

## 7.2 `extractor.py` — LLM Property Extraction

**What it does:** Takes raw document text and uses the LLM to pull out every numerical property — its value, unit, test standard, and a confidence score. The core intelligence of the ingestion pipeline.

Two extraction schemas depending on detected document type:

**TDS Schema (Technical Data Sheets):**
```
Input:  First 6,000 characters of document
Output: {
  material_name,
  extraction_confidence (0-1),
  properties: [{name, value, unit, confidence, context}],
  processing_conditions: [{name, value, confidence}]
}
```

**Paper Schema (Research Papers):**
```
Input:  First 8,000 characters of document
Output: {
  extraction_confidence (0-1),
  material_properties_mentioned: [{property, value, unit, confidence, context}],
  key_findings: [{finding, confidence}],
  methodology,
  research_objective
}
```

Document type is auto-detected by keyword frequency scoring. TDS keywords: "typical properties", "ISO ", "ASTM ", "melt flow", "tensile strength", "nominal". Paper keywords: "abstract", "doi:", "et al.", "methodology", "characterization".

**Chunking:** Text is split into 4,000-char chunks with 300-char overlap. Each chunk is processed independently and results are merged with deduplication.

**Example — real TDS extraction output:**
```
Material: Nylon 66 GF30 (30% Glass Fibre Reinforced)
Properties extracted:
  - Tensile Strength: 180 MPa  [confidence: 0.95, context: ISO 527]
  - Flexural Modulus: 9,000 MPa [confidence: 0.92, context: ISO 178]
  - Heat Deflection Temperature: 250°C [confidence: 0.88, context: ISO 75]
  - Density: 1.38 g/cm³ [confidence: 0.97, context: ISO 1183]
  - Water Absorption: 1.2% [confidence: 0.85, context: ISO 62]
```

## 7.3 `job_queue.py` — Background Processing

**What it does:** Manages the ingestion pipeline as a background priority queue so that uploads are non-blocking. The user can upload 50 files and immediately use the UI while processing happens behind the scenes. Jobs are persisted to Qdrant so they survive backend restarts.

```
File Received
     │
     ▼
Priority Assignment
  < 1MB  → HIGH   (processes first)
  1-10MB → MEDIUM
  > 10MB → LOW
     │
     ▼
Min-Heap Priority Queue
     │
     ▼ (single background thread)
process_job():
  1. extract_text()       ← pdfplumber / PyPDF2
  2. extract_from_text()  ← LLM → JSON
  3. upsert_document()    ← manifest to Qdrant
  4. upsert_property()×N  ← properties to Qdrant
  5. upsert_chunks()      ← text vectors to Qdrant
  6. auto KG edges        ← knowledge_graph edges
  7. job status → completed
```

Max retries: 3 per job. Jobs survive backend restarts (Qdrant persistence). Temp files deleted on completion.

## 7.4 `qdrant_store.py` — Storage Abstraction

**What it does:** Single class `QdrantStore` wrapping all 8 Qdrant collections behind a consistent Python API. All other modules write and read through this layer — nothing in the codebase calls Qdrant directly. This is the sole gateway to the database.

Key design decisions:
- All payloads are flat (no nested `metadata` key) — simpler filtering, no key collision issues
- File hash stored in `documents` collection for SHA-256 deduplication
- Chunk text stored in `doc_chunks` — full document can be reconstructed from chunks
- Property rows stored individually in `material_properties` — enables structured property queries (e.g. "all materials with tensile > 100 MPa")
- 1-dim dummy vectors for non-text collections (folders, jobs, sessions) — Qdrant requires a vector, so a placeholder is used

## 7.5 `knowledge_graph.py` — Graph-Enhanced Search

**What it does:** Builds a directed graph of relationships between materials, properties, and documents. When a query comes in, it doesn't just do a vector similarity search — it expands the results by walking the graph to find related materials and properties that a pure vector search would miss. Then re-ranks everything by importance.

```
Query Text
     │
     ▼
Vector Search (doc_chunks, k×2 results)
     │
     ▼
2-Hop Graph Expansion
  For each matched material node:
    - Follow all outgoing edges (HAS_PROPERTY, CONTAINS, etc.)
    - Follow all incoming edges
    - Add connected nodes to candidate set
     │
     ▼
Re-Rank All Candidates:
  score = 0.6 × vector_score
        + 0.3 × PageRank(node)   ← importance in graph
        + 0.1 × min(1, neighbours/10)  ← connectivity
     │
     ▼
Return Top-k Results
```

**Why this matters:** A document mentioning "DGEBA epoxy + MXene" might be connected via graph to 15 other documents that mention either ingredient separately. Pure vector search would miss them. Graph expansion finds related materials even when the query terms don't appear verbatim.

## 7.6 `orchestrator.py` — Autonomous Research Loop

**What it does:** The state machine that drives iterative experiment planning. Each iteration retrieves relevant context from the knowledge base, instructs the LLM to propose candidate configurations grounded in that context, scores them, and waits for researcher approval before the next iteration. Full breakdown in Section 10.

**Current limitation (Phase 7 target):** If the LLM returns malformed JSON, the orchestrator falls back to hardcoded configurations and uses `random.uniform()` for scoring. This is known and will be eliminated.

## 7.7 `experiment_runner.py` — Property Prediction

**What it does:** Given a proposed material configuration (name, composition, processing conditions), queries the knowledge base for all known properties of similar materials and uses the LLM to predict what properties the proposed configuration would likely have. Powers both the loop's scoring step and the manual "Predict" button in the Experiments view.

## 7.8 `chat.py` — Expert Chat Engine

**What it does:** Handles the RAG chat pipeline end-to-end. Takes the user's question, retrieves relevant document chunks via the knowledge graph, builds a full prompt with conversation history and retrieved context, streams the LLM response token-by-token to the browser, and persists the exchange to Qdrant.

Three roles with fundamentally different reasoning approaches:

| Role | Focus | When to Use |
|---|---|---|
| **Material Expert** | Technical analysis — values, units, standards, grade comparisons | "What is the tensile strength of PA66 GF30?" |
| **Technical Reviewer** | QA — gaps, inconsistencies, missing data, compliance | "Does this TDS fully meet ISO requirements?" |
| **Literature Researcher** | Synthesis — findings, methodology, research gaps | "Summarise what our indexed papers say about MXene in epoxy" |

Session memory: last 4 turns (8 messages) in context window, persisted to Qdrant across browser sessions.

---

# 8. Frontend — Component-by-Component Breakdown

## 8.1 Navigation Structure

```
╔══════════════════════════════════════════════════════╗
║ SIDEBAR (collapsible, 220px ↔ 56px)                   ║
║                                                        ║
║  Research    ← Main workspace (loop + dashboard)       ║
║  Papers      ← Document library + upload               ║
║  Experiments ← Kanban board for experiment tracking    ║
║  Results     ← Comparative analysis charts             ║
║  Decisions   ← Loop approval + reasoning view          ║
║  Chat        ← RAG expert chat                         ║
║                                                        ║
║  ● Ollama  online  qwen2.5:3b                          ║
║  ● Qdrant  online  N pts                               ║
║  ● Engine  online  N exps                              ║
╚══════════════════════════════════════════════════════╝
```

## 8.2 Research View — `GoalPanel`, `KnowledgePanel`, `ExperimentDashboard`, `ResultsPanel`, `DecisionPanel`

**What it does:** The main workspace. All five panels in one view — set the goal, see what the knowledge base knows, watch the loop run, review candidate scores, and approve or reject.

```
┌─────────────────────────────────────────────────────────────────┐
│ GOAL PANEL                                                        │
│ [Research goal text area]  Strength: ──●── 0.50                  │
│ [Start Loop] [Run Once]    Flexibility: ──●── 0.35               │
│                            Cost: ──●── 0.15                      │
├────────────────────┬────────────────────────────────────────────┤
│ KNOWLEDGE PANEL    │ EXPERIMENT DASHBOARD                        │
│ Papers | Insights  │ [candidate cards with scores]               │
│ [paper cards]      │ Composite: ████░░░ 0.73                     │
│ relevance scores   │ Strength:  ████░░░ 0.81                     │
│ property chips     │ Flexibility: ███░░░ 0.64                    │
├────────────────────┴────────────────────────────────────────────┤
│ RESULTS PANEL                │ DECISION PANEL                   │
│ [Recharts radar/trend]       │ Retrieve ▶ Generate ▶ Evaluate   │
│ Exp table: exp/actual/dev    │ ▶ Decide ▶ [APPROVE]             │
│ Deviation %: ████ pass/fail  │ Reasoning: "Config A achieves..." │
│                              │ Next hypothesis: [editable]       │
└──────────────────────────────┴──────────────────────────────────┘
```

- **GoalPanel:** Free-text research goal + three weight sliders (strength / flexibility / cost). Start Loop / Run Once buttons. Loop status badge.
- **KnowledgePanel:** Shows the most relevant papers from the indexed corpus given the current goal. Tabs for Papers and Insights. Property chips on each card.
- **ExperimentDashboard:** Shows all candidates from the current loop iteration as score cards. Composite score bar, individual dimension scores, iteration badge.
- **ResultsPanel:** Recharts radar and trend charts comparing predicted vs. actual values. Experiment table with deviation percentages, pass/fail indicators.
- **DecisionPanel:** Step-by-step loop stage indicator (Retrieve → Generate → Evaluate → Decide). Approve button. Editable hypothesis text. LLM reasoning paragraph.

## 8.3 Papers View — `PapersView`

**What it does:** The document management interface. Upload files or folders, see all indexed documents in a table, view extraction details for any document, bulk delete, monitor the job queue.

```
┌─────────────────────────────────────────────────────────────────┐
│ [47]          [12]          [35]         [2,847]                  │
│ Total Docs    TDS           Papers       Qdrant Points            │
├─────────────────────────────────────────────────────────────────┤
│ [Upload File] [Upload Folder] [Scan Path]                        │
├─────────────────────────────────────────────────────────────────┤
│ ☐ │ Filename          │ Type   │ Status    │ Props │ Date        │
│───┼───────────────────┼────────┼───────────┼───────┼────────────│
│ ☑ │ nylon66_gf30.pdf  │ TDS    │ done      │  24   │ Apr 2026   │
│ ☐ │ mxene_epoxy.pdf   │ Paper  │ done      │  18   │ Apr 2026   │
│ ☐ │ processing.pdf    │ TDS    │ running   │  --   │ Apr 2026   │
├─────────────────────────────────────────────────────────────────┤
│ JOB QUEUE                                                         │
│  HIGH  nylon66.pdf  ████████████ 100%  completed   2.1s         │
│  MED   paper.pdf    ████░░░░░░░░  40%  running     4.2s         │
└─────────────────────────────────────────────────────────────────┘
```

Clicking any document opens a detail modal with tabs: Properties (all extracted values), Methodology, Key Findings, Limitations, and Raw text.

## 8.4 Experiments View — `ExperimentsPanel`

**What it does:** Kanban board for tracking all experiments. Three columns by status. Click any card to open full detail, log results, or get AI suggestions for next configuration.

```
┌─────────────────────────────────────────────────────────────────┐
│ Experiments  [Search...]                   12 total  [+ New]     │
├───────────────────┬───────────────────┬─────────────────────────┤
│ QUEUED       (3)  │ RUNNING      (1)  │ COMPLETED          (8)  │
│                   │                   │                         │
│ ┌─────────────┐  │ ┌─────────────┐  │ ┌─────────────┐         │
│ │ Test Run 4  │  │ │ EPDM Test   │  │ │ PA66 Trial  │         │
│ │ Nylon 66    │  │ │ MXene-Epoxy │  │ │ ████████░░  │         │
│ │             │  │ │ Running…    │  │ │ 82%  Iter 3 │         │
│ └─────────────┘  │ └─────────────┘  │ └─────────────┘         │
│                   │                   │ ┌─────────────┐         │
│ ┌─────────────┐  │                   │ │ PC Blend    │         │
│ │ Config B    │  │                   │ │ ████████████│         │
│ │ PC+Impact   │  │                   │ │ 91%  Iter 5 │         │
└─┴─────────────┴──┴───────────────────┴─┴─────────────┴─────────┘
```

## 8.5 Chat View — `ChatPanel`

**What it does:** The RAG chat interface. Streaming responses, role selector, source document list after each answer.

```
┌─────────────────────────────────────────────────────────────────┐
│ [Material Expert ✓] [Technical Reviewer] [Literature Researcher] │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  You: What materials in our database have tensile strength       │
│       above 100 MPa?                                             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Based on the indexed documents, the following materials    │   │
│  │ meet your criterion:                                       │   │
│  │                                                            │   │
│  │  • Nylon 66 GF30: 180 MPa (ISO 527) [nylon66_gf30.pdf]   │   │
│  │  • POM Delrin 500: 138 MPa (ASTM D638) [acetal_tds.pdf]  │   │
│  │  • Carbon Fibre Epoxy: 310 MPa (measured) [paper_cf.pdf] │   │
│  │                                                            │   │
│  │  Sources: nylon66_gf30.pdf  acetal_tds.pdf  paper_cf.pdf  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│ [Ask a question about your materials...              ] [Send →]  │
└─────────────────────────────────────────────────────────────────┘
```

---

# 9. Data Flows

## 9.1 Document Ingestion Flow

```
User selects PDF(s)
        │
        ▼
POST /api/documents/upload
        │
        ▼
job_queue.create_job()
   → Priority: HIGH (<1MB) / MEDIUM (1-10MB) / LOW (>10MB)
   → Status: QUEUED
   → Persisted to Qdrant job_status
        │
        ▼ (background thread, non-blocking)
parser.extract_text()
   → pdfplumber (primary)
   → PyPDF2 (fallback if pdfplumber fails)
   → Returns: plain text string
        │
        ▼
extractor.detect_document_type()
   → Keyword frequency scoring
   → Returns: "tds" or "paper"
        │
        ▼
extractor.extract_from_text()
   → Truncate: TDS→6000 chars, Paper→8000 chars
   → Split into 4000-char chunks (300 overlap)
   → For each chunk: LLM call (json_mode=True, temp=0)
   → Merge results (deduplicate by name+value key)
   → Returns: merged extraction result
        │
        ├──→ qdrant_store.upsert_document()
        │       documents collection
        │       Fields: filename, hash, type, status, material_name,
        │               methodology, key_findings, confidence
        │
        ├──→ qdrant_store.upsert_property() × N
        │       material_properties collection
        │       One row per extracted property
        │
        ├──→ qdrant_store.upsert_chunks()
        │       doc_chunks collection
        │       2000-char chunks, 768-dim embeddings
        │
        └──→ knowledge_graph.auto_extract_edges()
                knowledge_edges collection
                Creates HAS_PROPERTY edges (weight = confidence)
        │
        ▼
job status → COMPLETED
Browser SSE stream receives final job update
```

## 9.2 Chat Query Flow

```
User types question: "What filler gives best EMI shielding?"
        │
        ▼
POST /api/chat  {query, role, session_id}
        │
        ▼
chat.get_relevant_context(query, limit=5)
        │
        ├── knowledge_graph.graph_aware_search(query, k=5)
        │         │
        │         ▼
        │   Vector search on doc_chunks (cosine, k×2 results)
        │         │
        │         ▼
        │   2-hop graph expansion from matched nodes
        │         │
        │         ▼
        │   Re-rank: 0.6×vector + 0.3×PageRank + 0.1×connectivity
        │         │
        │         ▼
        │   Return top-5 chunks with metadata
        │
        ├── ChatSession.get_context()  ← last 4 turns from Qdrant
        │
        ▼
Build full prompt:
  [role system prompt]
  [conversation history]
  [retrieved document chunks]
  [user question]
        │
        ▼
LLM inference (qwen2.5:3b, temp=0.1, streaming)
        │
        ▼
ChatSession.add_message() → save to Qdrant chat_sessions
        │
        ▼
Stream tokens to browser + return source document list
```

## 9.3 Loop Iteration Flow

```
User sets goal: "Maximise tensile strength in rubber compound"
User sets weights: Strength 60%, Flexibility 30%, Cost 10%
User clicks "Start Loop"
        │
        ▼
POST /api/loop/start {goal, weights}
        │
        ▼ (Step 1: Retrieve)
knowledge_graph.graph_aware_search(goal + hypothesis, k=5)
        │
        ▼ (Step 2: Generate)
LLM generates 3 candidate configurations
  → Each candidate: material_name, composition, processing, hypothesis
        │
        ▼ (Step 3: Evaluate)
For each candidate:
  predict_properties(material_name, composition, conditions)
  calculate_composite_score(predicted, weights)
  → Composite = strength×w_s + flexibility×w_f + cost×w_c
        │
        ▼ (Step 4: Decide)
Sort candidates by composite_score DESC
LLM generates reasoning paragraph + next_hypothesis
        │
        ▼
Persist to Qdrant experiments collection
        │
        ▼ (Step 5: Awaiting Approval)
UI shows: candidates, scores, reasoning, next hypothesis
User can: Edit hypothesis | Approve | Stop
        │
        ▼ (on Approve)
Loop back to Step 1 with updated hypothesis
Iteration counter increments
```

---

# 10. The Autonomous Research Loop

The research loop is the platform's core differentiator. It operationalises the scientific method as a software state machine.

## 10.1 Conceptual Model

```
 Human researcher's internal process:
   Read literature → Form hypothesis → Design experiment
     → Run experiment → Analyse results → Refine hypothesis → Repeat

 Platform's equivalent:
   Retrieve from KB → Generate hypothesis → Predict & score
     → Present to researcher → Researcher approves → Next iteration
```

The loop does not replace the researcher. It accelerates the thinking step between "what do we know?" and "what should we try next?" by surfacing the most relevant knowledge and proposing justified candidates with scores.

## 10.2 State Machine

```
          ┌─────────────────────────────────────┐
          │               IDLE                   │
          │  No active loop. Last state persisted│
          └──────────────┬──────────────────────┘
                         │
                         │ POST /api/loop/start
                         │ {goal, weights}
                         │
          ┌──────────────▼──────────────────────┐
          │             RUNNING                  │
          │  Step 1: Retrieve (KB search)        │
          │  Step 2: Generate (LLM candidates)   │
          │  Step 3: Evaluate (predict + score)  │
          │  Step 4: Decide   (rank + reason)    │
          └──────────────┬──────────────────────┘
                         │
                         │ Iteration complete
                         │
          ┌──────────────▼──────────────────────┐
          │          AWAITING APPROVAL           │
          │  Shows: candidates, scores,           │
          │  reasoning, next hypothesis           │
          │                                      │
          │  User actions available:             │
          │  • Edit next hypothesis text          │
          │  • Approve → back to RUNNING          │
          │  • Stop → STOPPED                     │
          └──────┬─────────────────────┬─────────┘
                 │ approve()           │ stop()
     ┌───────────▼──────┐    ┌────────▼─────────┐
     │    RUNNING       │    │     STOPPED       │
     │  (next iter)     │    │  State preserved  │
     └──────────────────┘    │  in memory        │
                             └──────────────────┘
```

## 10.3 Optimization Scoring

The composite score determines which candidate "wins" each iteration:

```
composite_score = (strength_score  × w_strength)
                + (flexibility_score × w_flexibility)
                + (cost_score       × w_cost)

where:
  strength_score    = min(1.0, predicted_tensile / target_tensile)
  flexibility_score = min(1.0, predicted_elongation / target_elongation)
  cost_score        = placeholder (Phase 7: replace with real property data)

Default weights: w_strength=0.50, w_flexibility=0.35, w_cost=0.15
User-configurable via GoalPanel sliders.
```

## 10.4 Iteration History

Every iteration is persisted to Qdrant's `experiments` collection with full detail: all candidates, all scores, LLM reasoning, next hypothesis. The history is available to the LLM in subsequent iterations — it can see what has been tried and avoid repeating failed directions.

---

# 11. Knowledge Base & Retrieval System

## 11.1 Two-Layer Storage

```
LAYER 1 — Structured Properties (material_properties collection)
  What it contains: Discrete property rows
  Example: {material: "Nylon 66", property: "Tensile Strength",
             value: 180, unit: "MPa", confidence: 0.95,
             context: "ISO 527, dry as moulded"}
  Use case: Structured queries ("find all materials with tensile > 100 MPa")
  Query type: Qdrant payload filter

LAYER 2 — Semantic Chunks (doc_chunks collection)
  What it contains: 2000-char text passages
  Example: "The addition of 30% glass fibre reinforcement significantly
             improves the mechanical properties of polyamide 66. Under dry
             conditions, tensile strength reaches 180 MPa..."
  Use case: Natural language questions about context, methodology, trade-offs
  Query type: Cosine similarity (768-dim vector)
```

## 11.2 Knowledge Graph Topology

```
                    [material: Nylon 66 GF30]
                    /         |           \
          HAS_PROPERTY    HAS_PROPERTY   HAS_PROPERTY
                /               |               \
    [prop: Tensile    [prop: Heat Deflect   [prop: Density]
     Strength 180MPa]   Temp 250°C]          1.38 g/cm³]
          |
     MEASURED_BY
          |
    [doc: nylon66_tds.pdf]
          |
     SIMILAR_TO
          |
    [material: Nylon 66 GF50]
```

Querying "Nylon 66 properties" returns not just direct vector matches but also all connected materials (SIMILAR_TO edges) and their properties, weighted by PageRank importance.

## 11.3 Why RAG Over Fine-Tuning

The system uses Retrieval-Augmented Generation (RAG) rather than a fine-tuned model. This is the correct architecture for this use case:

**RAG advantages:**
- Every new document immediately improves answer quality — no retraining required
- The model always has access to the most current data in the corpus
- Source attribution is possible — the model can cite which document it drew from
- No GPU training infrastructure required
- Scales linearly with corpus size

**When fine-tuning becomes relevant:**
After significant corpus accumulation, the platform will have a large dataset of human-verified property extractions (researchers correcting LLM outputs via the Document Details modal). This ground-truth data can then be used to fine-tune the extraction model specifically on the organisation's document vocabulary. This is planned as a later phase — the prerequisite is the data, which is being accumulated now by every upload and verification cycle.

---

# 12. API Surface

51 endpoints across 8 domains. Full REST + SSE. Auto-documented at `http://localhost:8000/docs`.

```
DOCUMENTS (12 endpoints)
  POST   /api/documents/upload         ← upload a PDF
  GET    /api/documents                ← list all documents
  GET    /api/documents/{id}           ← get document detail
  DELETE /api/documents/{id}           ← delete one document
  POST   /api/documents/bulk-delete    ← delete multiple
  GET    /api/documents/{id}/properties ← extracted properties
  POST   /api/documents/{id}/reprocess ← re-run extraction
  GET    /api/documents/{id}/extraction ← raw extraction result
  POST   /api/documents/reprocess-all  ← reprocess entire corpus
  GET    /api/parsed                   ← legacy parsed list
  GET    /api/parsed/{id}
  DELETE /api/parsed/{id}

JOBS (4 endpoints)
  GET    /api/jobs                     ← all jobs
  GET    /api/jobs/{id}                ← single job status
  GET    /api/jobs/{id}/stream         ← SSE live progress
  DELETE /api/jobs/{id}                ← cancel job

BULK OPERATIONS (5 endpoints)
  POST   /api/bulk-scan                ← scan folder path
  POST   /api/bulk-scan-ui             ← scan from UI upload
  POST   /api/bulk-scan-recursive      ← recursive SSE scan
  POST   /api/bulk-parse               ← bulk parse SSE
  POST   /api/bulk-delete-manifest

EXPERIMENTS (11 endpoints)
  POST   /api/experiments              ← create experiment
  GET    /api/experiments              ← list all
  GET    /api/experiments/{id}         ← get one
  PUT    /api/experiments/{id}         ← update
  POST   /api/experiments/{id}/results ← log actual results
  DELETE /api/experiments/{id}
  GET    /api/experiments/suggest      ← AI suggestions
  POST   /api/experiments/{id}/predict ← predict properties
  POST   /api/experiments/{id}/suggest ← suggest next config
  GET    /api/experiments/{id}/history ← iteration history
  POST   /api/experiments/{id}/complete ← mark complete

RESEARCH LOOP (6 endpoints)
  GET    /api/loop/status              ← current loop state
  POST   /api/loop/start               ← start loop
  POST   /api/loop/iterate             ← run next iteration
  POST   /api/loop/approve             ← approve current result
  POST   /api/loop/stop                ← stop loop
  PUT    /api/loop/hypothesis          ← edit hypothesis text

CHAT (4 endpoints)
  POST   /api/chat                     ← send message (SSE stream)
  GET    /api/chat/sessions            ← list sessions
  GET    /api/chat/sessions/{id}/history ← get session history
  DELETE /api/chat/sessions/{id}       ← delete session

KNOWLEDGE GRAPH (3 endpoints)
  GET    /api/graph/stats              ← node/edge counts
  GET    /api/graph/connections/{material} ← material connections
  GET    /api/graph/materials          ← all known materials

SYSTEM (7 endpoints)
  GET    /                             ← root
  GET    /health                       ← health check
  GET    /api/stats                    ← document/experiment counts
  GET    /api/search                   ← semantic search
  GET    /api/materials/search         ← material-specific search
```

---

# 13. Current Limitations & Honest Assessment

### 13.1 Loop Fallback Logic (Critical — Phase 7)
If the LLM fails to generate valid JSON during candidate generation, the orchestrator falls back to three hardcoded configurations (Polycarbonate, EPDM, Nylon 66). These are not derived from the actual knowledge base. The scoring in the evaluate step uses `random.uniform()` as a fallback when property prediction fails.

**This makes the loop unreliable for real research use. It is the primary target of Phase 7.**

### 13.2 Extraction Vocabulary (Critical — Phase 6)
The current extraction prompts are tuned for general polymer properties (tensile, density, melt flow). Specialist properties — EMI shielding effectiveness (dB), electrical conductivity (S/m), thermal conductivity (W/mK), glass transition temperature (Tg), filler loading (vol%, wt%, phr) — may not be extracted correctly.

**This is the primary target of Phase 6.**

### 13.3 Experiment Schema is Hardcoded
The experiment system tracks only tensile strength and elongation. Any other property domain requires code changes.

**This is the primary target of Phase 8.**

### 13.4 Scanned PDFs
No OCR. Image-only PDFs (scanned without a text layer) produce empty extractions. The job succeeds but yields zero properties. Requires Tesseract or PaddleOCR as a pre-processing step.

### 13.5 Cost Scoring is a Placeholder
The cost dimension in the composite score is `0.7` across all materials. Real cost data requires either manual input or supplier pricing integration.

### 13.6 Context Window Truncation
The extractor processes only the first 6,000–8,000 characters of a document. Long documents (>30 pages) may have important data on later pages that is missed. Full-document chunked extraction is planned.

### 13.7 Single User
The platform runs on localhost with no authentication. This is intentional for the current phase. Multi-user deployment is deferred to Phase 9 once core quality is proven.

---

# 14. Strategic Roadmap

## Completed Phases ✅

### Phase 1 — Core Ingestion Pipeline
PDF upload → text extraction → LLM property extraction → Qdrant storage. Priority job queue. SHA-256 dedup. Job status persistence. Basic React UI.

### Phase 2 — Research Loop & Experiments
Autonomous loop state machine. Experiment runner with composite scoring. Knowledge graph (NetworkX + Qdrant). Full experiment CRUD. Human-in-the-loop approval gate.

### Phase 3 — Chat & Knowledge Inspection
RAG chat with 3 expert roles. SSE streaming. Session memory. Knowledge panel. Document details modal with all tabs (properties, methodology, findings, limitations, raw data).

### Phase 4 — Bug Fixes & Data Quality
Folder upload fix. Chat blank-screen crash fix. Re-extract always-refresh fix. Methodology/findings pipeline fixed end-to-end. Bulk delete endpoints + UI.

### Phase 5 — UI/UX Overhaul
Electric Indigo glassmorphism palette. Collapsible sidebar. Page transition animations. Experiments kanban board (3-column). Stat cards. Frosted topbar. Radial gradient background.

---

## Immediate Next Phases (2-Week Target) 🔲

### Phase 6 — Domain Intelligence (Extraction Overhaul)
**Goal:** Make the extractor understand the actual vocabulary of advanced materials research.
**Timeline:** Week 1

The current extraction prompts are written for general injection-moulded thermoplastics. The extractor needs to recognise:

- EMI shielding effectiveness (SE, dB, at specific frequencies)
- Electrical conductivity (S/m, S/cm)
- Thermal conductivity (W/mK)
- Glass transition temperature (Tg, °C)
- Filler loading (vol%, wt%, phr)
- Aspect ratio of fillers
- Cure conditions (resin/hardener ratio, cure temperature, post-cure time)
- Dielectric constant, loss tangent
- Specific surface area (BET, m²/g)
- Interlaminar shear strength (ILSS)

Changes required:
- `extractor.py` — expanded system prompts with full domain vocabulary
- `config.py` — updated keyword lists for improved document type detection
- No schema changes to Qdrant — properties already stored generically

**Expected outcome:** Papers on nanocomposites, 2D material fillers (MXene, graphene), functional coatings extract correctly with appropriate property names, units, and test conditions.

---

### Phase 7 — Orchestrator Intelligence (Loop Overhaul)
**Goal:** Replace all placeholder and random logic with genuine literature-grounded hypothesis generation.
**Timeline:** Week 1

Changes required:
- `orchestrator.py` — eliminate all fallback heuristics. If the LLM returns malformed JSON, retry or pause — never substitute hardcoded configs
- Candidate generation must only propose materials and configurations supported by at least one document in Qdrant
- Each candidate must cite the source documents it was derived from
- `experiment_runner.py` — scoring grounded in actual extracted property values from Qdrant, not placeholder prediction
- Generate 5 candidates, score all, present top 3 with full reasoning

**Example of target behaviour after Phase 7:**
```
Iteration 3 — Goal: "High EMI shielding with retained tensile strength"

Candidate A — Ti3C2Tx MXene / DGEBA Epoxy at 3 vol%
  Derived from: [mxene_epoxy_2024.pdf, ti3c2_review.pdf]
  Predicted EMI SE: 34–38 dB (interpolated from 2.5 vol%=31dB, 4 vol%=42dB)
  Predicted Tensile: 58–65 MPa (epoxy baseline 55 MPa + minor filler effect)
  Composite Score: 0.81

Candidate B — MXene + CNT Hybrid / Epoxy at 2 vol% total
  Derived from: [hybrid_emi_paper.pdf]
  Predicted EMI SE: 40–45 dB (synergistic effect documented)
  Predicted Tensile: 52–58 MPa (slight reduction from CNT agglomeration risk)
  Composite Score: 0.79

Reasoning: Candidate A is recommended for Iteration 4. The pure MXene
system offers more predictable property scaling based on 3 papers in the
knowledge base. The hybrid approach (B) shows higher EMI SE but introduces
dispersion uncertainty not yet characterised in this lab's process conditions.
```

---

### Phase 8 — Flexible Experiment Schema
**Goal:** Make the experiment system domain-agnostic — usable for any material type and any set of measured properties.
**Timeline:** Week 2

Currently the experiment schema hardcodes tensile strength and elongation as the only metrics.

Changes required:
- Frontend: experiment creation modal — dynamic property field builder (add any metric: name + target value + unit + weight)
- Frontend: domain presets — one-click load a standard property set (e.g. "EMI Shielding Experiment" pre-fills SE, conductivity, density)
- Backend: `expected_output` and `actual_output` become arbitrary key-value maps, not hardcoded fields
- Backend: scoring weights configurable per-experiment, not global
- Backend: `experiment_runner.py` — prediction prompt adapts to whatever properties the experiment targets

**Example of target flexibility:**
```
Experiment: Ti3C2Tx EMI Shielding Trial
Properties tracked:
  - EMI SE (target: 35 dB) [weight: 0.50]
  - Tensile Strength (target: 55 MPa) [weight: 0.30]
  - Thermal Conductivity (target: 0.8 W/mK) [weight: 0.15]
  - Density (target: <1.5 g/cm³) [weight: 0.05]
```

---

## Later Phases 🔲

### Phase 9 — Multi-User & Company Deployment
Move from single-user local tool to shared company-wide system. JWT-based auth, user roles (Admin / Researcher / Viewer), project namespaces (`project_id` field on all Qdrant collections), GPU server deployment with Nginx reverse proxy.

### Phase 10 — Material Discovery Engine
Transform from passive Q&A to active discovery. Property-based structured search ("find materials with SE > 30 dB AND tensile > 50 MPa"). Research gap analysis — build filler-matrix coverage matrix and identify unexplored combinations. Inverse design — given target property profile, predict composition.

### Phase 11 — Fine-Tuned Extraction Model
After accumulating a large corpus of human-verified extractions (researchers correcting LLM outputs via the Document Details modal), fine-tune qwen2.5:3b on `(document_chunk, extracted_properties)` pairs. Deploy as a custom Ollama model. Expected improvement: extraction confidence from ~0.75 to ~0.90+.

### Phase 12 — Desktop Application
Package as a zero-install `.exe` using Tauri (already scaffolded in the project). Auto-launch all services on open, graceful shutdown on close. Windows NSIS installer for distribution to lab computers without IT involvement.

---

# 15. Infrastructure Path to Company-Wide Deployment

## Current State
```
Developer Machine (Windows 11, RTX 3050 4GB VRAM)
  └── All services on localhost
  └── Single user
  └── No auth
  └── ~35-50 tok/s (3b model, full VRAM)
  └── Qdrant on-disk at local path
```

## Recommended Server Spec (10-20 concurrent users)
```
GPU Server:
  CPU: Intel Xeon or AMD EPYC (16+ cores)
  RAM: 64GB+
  GPU: NVIDIA RTX 4090 (24GB VRAM) or A100 (40GB)
       → Fits 14b model fully in VRAM at Q4_K_S
       → Handles multiple concurrent inference requests
  Storage: 2TB NVMe (Qdrant data + uploaded PDFs)
  OS: Ubuntu 22.04 LTS

Software stack:
  Ollama (CUDA build)
  Qdrant (Docker, persistent volume)
  FastAPI (Gunicorn + Uvicorn workers, 4 workers)
  Nginx (reverse proxy, HTTPS termination)
  Frontend (Nginx static serve of Vite build)
```

## Deployment Timeline
```
Now → 2 weeks:
  Domain intelligence + orchestrator fix + flexible experiments
  Core quality proven on single machine

2-8 weeks:
  JWT auth + user accounts
  Project namespaces in Qdrant
  Deploy to shared GPU server on internal network
  Migrate Qdrant snapshot to server (zero data loss)

8-16 weeks:
  Material discovery features
  Property-based search UI
  Research gap analysis
  Fine-tune extraction model on accumulated verified data

16+ weeks:
  Inverse design capability
  Export to publication tables
  API access for lab instruments / ERP systems
  Desktop app for offline / air-gapped labs
```

## Data Migration Path
The current Qdrant data (all indexed documents, experiments, chat sessions) can be exported using Qdrant's snapshot API and imported to the server instance with zero data loss. No schema changes are required for Phases 6–8 — all new property types fit into the existing flat payload model.

---

*Document prepared: April 2026*
*Platform version: v1.0*
*Status: Active development — 2-week sprint in progress*
