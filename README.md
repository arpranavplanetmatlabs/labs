# Planet Material Labs — AI Research Assistant

> An autonomous, AI-powered materials science research platform built for **Planet Material Labs**. It ingests technical datasheets and research papers, extracts structured material properties using a local LLM, maintains a semantic knowledge base, drives an autonomous experiment loop, and provides a RAG-powered chat interface — all running 100% offline on local hardware.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [Backend Module Reference](#4-backend-module-reference)
5. [Frontend Component Reference](#5-frontend-component-reference)
6. [Qdrant Schema — 8 Collections](#6-qdrant-schema--8-collections)
7. [Data & Ingestion Pipeline](#7-data--ingestion-pipeline)
8. [Autonomous Research Loop](#8-autonomous-research-loop)
9. [Chat System](#9-chat-system)
10. [API Reference](#10-api-reference)
11. [Project Phases](#11-project-phases)
12. [Setup & Running](#12-setup--running)
13. [Directory Structure](#13-directory-structure)
14. [Known Limitations & Design Decisions](#14-known-limitations--design-decisions)

---

## 1. Project Overview

Planet Material Labs is developing AI tooling to accelerate materials research. This assistant is the first internal platform — it replaces manual, spreadsheet-driven property lookup and hypothesis generation with a fully automated pipeline.

**What it does end-to-end:**

```
PDF Upload → Text Extraction → LLM Property Extraction → Qdrant Storage
      ↓
Semantic Search + Knowledge Graph
      ↓
Autonomous Experiment Loop (Goal → Hypothesis → Predict → Score → Approve → Next)
      ↓
RAG Chat (Materials Expert / Technical Reviewer / Literature Researcher)
```

**Hardware target:** Windows 11, NVIDIA RTX 3050 (4GB VRAM), 16GB RAM. Everything runs locally — no API keys, no cloud, no data leaves the machine.

---

## 2. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Frontend framework | React | 18, via Vite |
| Frontend bundler | Vite + Tauri CLI | Tauri used for future desktop packaging |
| Styling | Pure CSS (custom design system) | Electric Indigo glassmorphism palette |
| Icons | lucide-react | — |
| Charts | Recharts | Used in ResultsPanel |
| Backend framework | FastAPI | Python 3.11+ |
| ASGI server | Uvicorn | — |
| LLM runtime | Ollama | localhost:11434 |
| LLM model | `qwen2.5:14b-instruct-q4_K_S` | GGUF Q4_K_S, CUDA-accelerated |
| Embedding model | `nomic-embed-text` | 768-dimensional vectors |
| Vector database | Qdrant | localhost:6333, local on-disk storage |
| Qdrant Python client | `qdrant-client` | — |
| LangChain (RAG) | `langchain-ollama`, `langchain-qdrant` | Used in chat.py |
| Knowledge graph | NetworkX | In-memory, rebuilt from Qdrant every 300s |
| PDF parsing | pdfplumber + PyPDF2 | Fallback chain |

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        REACT FRONTEND  :5173                         │
│                                                                      │
│  Sidebar   GoalPanel   KnowledgePanel   ExperimentDashboard          │
│  PapersView  ExperimentsPanel (Kanban)  ChatPanel  DecisionPanel     │
│  ResultsPanel  DocumentDetails                                       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP / SSE  (localhost:8000)
┌────────────────────────────▼─────────────────────────────────────────┐
│                        FASTAPI BACKEND  :8000                        │
│                                                                      │
│  main.py ──────── REST + SSE API surface                             │
│  │                                                                   │
│  ├── job_queue.py ─── Priority queue, background worker thread       │
│  │       └── process_job()                                           │
│  │             ├── parser.py      (PDF → raw text)                   │
│  │             ├── extractor.py   (text → JSON schema via LLM)       │
│  │             └── qdrant_store.py (upsert to all collections)       │
│  │                                                                   │
│  ├── orchestrator.py ── Autonomous loop state machine                │
│  │       └── experiment_runner.py (predict + score)                  │
│  │                                                                   │
│  ├── chat.py ──────── RAG chat with roles + session memory           │
│  │       └── qdrant_mgr.py (semantic search)                         │
│  │                                                                   │
│  ├── knowledge_graph.py ── NetworkX graph over Qdrant edges          │
│  ├── crawler.py ─────── Recursive folder scanner                     │
│  └── qdrant_store.py ── Single storage abstraction (all 8 cols)      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────┐
│                    QDRANT  :6333  (local on-disk)                    │
│                                                                      │
│  documents · doc_chunks · material_properties · experiments          │
│  knowledge_edges · scanned_folders · job_status · chat_sessions      │
└──────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────┐
│                    OLLAMA  :11434  (CUDA)                             │
│                                                                      │
│  qwen2.5:14b-instruct-q4_K_S   (LLM — property extraction, chat)    │
│  nomic-embed-text               (embeddings — 768-dim)               │
└──────────────────────────────────────────────────────────────────────┘
```

### Request flow — document upload

```
Browser → POST /api/documents/upload
  → job_queue: create_job() → queue_job()
  → background worker: process_job()
      → parser.extract_text()          # pdfplumber / PyPDF2
      → extractor.extract_from_text()  # Ollama LLM → JSON
      → extractor.extract_properties_list()   # flatten schema
      → qdrant_store.upsert_document()         # documents collection
      → qdrant_store.upsert_property() × N     # material_properties
      → qdrant_store.upsert_chunks()           # doc_chunks (768-dim vectors)
  → Browser polls GET /api/jobs/{job_id} or SSE /api/jobs/{job_id}/stream
```

### Request flow — chat message

```
Browser → POST /api/chat
  → chat.py: ChatSession.add_message()
  → qdrant_mgr.search(query, limit=5)   # cosine sim on doc_chunks
  → KnowledgeGraphManager.expand()      # 2-hop PageRank expansion (optional)
  → build prompt with context + role
  → OllamaLLM.stream()                  # token-by-token SSE back to browser
  → ChatSession._save_to_qdrant()       # persist turn to chat_sessions
```

---

## 4. Backend Module Reference

### `config.py`
Central configuration — all URLs, paths, collection names, and model identifiers in one place. No hardcoded strings anywhere else.

```python
LLM_MODEL   = "qwen2.5:14b-instruct-q4_K_S"
EMBED_MODEL = "nomic-embed-text"
QDRANT_URL  = "http://localhost:6333"
OLLAMA_BASE = "http://localhost:11434"
```

### `main.py`
FastAPI application. Registers all HTTP and SSE routes, runs Qdrant collection initialization on startup, and starts the job queue worker. Currently at v0.5.0 API surface.

**Key responsibilities:**
- `POST /api/documents/upload` — receives PDF, hands to job queue
- `GET /api/documents` / `GET /api/documents/{id}` — list and fetch documents with full payload (including `methodology`, `key_findings`, `processing_conditions`, `research_objective`)
- `DELETE /api/documents/{id}` — single document delete
- `POST /api/documents/bulk-delete` — batch delete by ID list
- `POST /api/documents/{id}/reprocess` — re-run LLM extraction on existing file
- `GET/POST /api/experiments` — CRUD for experiments
- `POST /api/experiments/{id}/predict` — LLM property prediction
- `POST /api/experiments/{id}/suggest` — next configuration suggestions
- `POST /api/experiments/{id}/complete` — mark completed with actual output
- `POST /api/loop/start`, `/iterate`, `/approve`, `/stop` — orchestrator control
- `PUT /api/loop/hypothesis` — edit pending hypothesis
- `POST /api/chat`, `GET /api/chat/sessions` — RAG chat
- `POST /api/folders/scan` — trigger recursive folder crawl
- `GET /api/stats` — live counts for sidebar badges

### `parser.py`
PDF → plain text. Uses `pdfplumber` as primary, falls back to `PyPDF2`. Handles scanned-only PDFs gracefully (returns empty string, logs warning). No OCR currently.

### `extractor.py`
LLM-based structured extraction. Two modes:

| Mode | Input | LLM Output Schema |
|---|---|---|
| TDS | Technical Data Sheet text | `material_name`, `extraction_confidence`, `properties[]`, `processing_conditions[]` |
| Paper | Research paper text | `extraction_confidence`, `material_properties_mentioned[]`, `key_findings[]`, `methodology`, `research_objective` |

`extract_from_text()` — calls Ollama, parses JSON response, handles malformed output.
`extract_properties_list()` — normalises both schemas into a flat list of `{name, value, unit, confidence, context}` dicts.

### `llm.py`
Thin wrapper around the Ollama HTTP client. Exposes `get_client()` which returns a connection-pooled instance. Also re-exports `LLM_MODEL` so other modules don't import from `config` directly.

### `qdrant_store.py`
The single storage abstraction for all 8 Qdrant collections. Key methods:

| Method | Collection | Description |
|---|---|---|
| `upsert_document()` | `documents` | Create/update document manifest. Accepts `methodology`, `research_objective`, `key_findings`, `processing_conditions`. |
| `update_document_properties_count()` | `documents` | Patch property count + research fields after re-extraction. |
| `upsert_chunks()` | `doc_chunks` | Split text → 2000-char chunks with 200-char overlap, embed with `nomic-embed-text`, store. |
| `upsert_property()` | `material_properties` | One point per extracted property row. |
| `get_all_documents()` | `documents` | Full list with payload. |
| `get_document_by_id()` | `documents` | Single document fetch. |
| `delete_document_by_id()` | `documents` | Remove document + cascade to chunks. |
| `get_all_file_hashes()` | `documents` | For deduplication in crawler. |
| `upsert_experiment()` | `experiments` | Store experiment record. |
| `get_all_experiments()` | `experiments` | List with payload. |
| `get_chat_session()` / `save_chat_session()` | `chat_sessions` | Persist conversation turns. |

Embedding dimension: **768**. All text vectors use `nomic-embed-text`. Non-text collections (`scanned_folders`, `job_status`) use a 1-dim dummy vector.

### `qdrant_mgr.py`
Higher-level search wrapper used by `chat.py` and `experiment_runner.py`. Exposes `search(query, limit)` which embeds the query, runs cosine search on `doc_chunks`, and returns ranked results with metadata.

### `job_queue.py`
In-process priority queue with a single background worker thread.

**Priority tiers (by file size):**
- HIGH: < 1 MB
- MEDIUM: 1–10 MB
- LOW: > 10 MB

Jobs are persisted to the `job_status` Qdrant collection so they survive backend restarts. Each job transitions through: `PENDING → QUEUED → RUNNING → COMPLETED | FAILED | CANCELLED`.

`process_job()` is the core pipeline function — it calls parser → extractor → qdrant_store, then updates the job status record. It extracts and persists `methodology`, `key_findings`, `processing_conditions`, and `research_objective` to the document manifest.

### `orchestrator.py`
The autonomous research loop state machine.

**States:** `idle → running → awaiting_approval → (loop | stopped)`

**Loop iteration steps (shown in UI progress bar):**
1. **Retrieve** — semantic search for relevant materials context from Qdrant
2. **Generate** — LLM generates a hypothesis for the next experiment configuration
3. **Evaluate** — `experiment_runner.predict_properties()` scores the hypothesis
4. **Decide** — pick best candidate, compute composite score
5. **Approve** — pauses and waits for human approval before next iteration

**Composite score formula:**
```
score = (strength × w_strength) + (flexibility × w_flexibility) + (cost_factor × w_cost)
```
Weights are set by the user in `GoalPanel` sliders (default: 0.50 / 0.35 / 0.15).

Loop state is fully thread-safe (`threading.Lock`). The full history of all iterations is kept in memory during a session.

### `experiment_runner.py`
Handles two LLM tasks for individual experiments:

- `predict_properties(material_name, composition, conditions)` — pulls relevant Qdrant context, builds prompt, returns predicted property values with confidence
- `calculate_composite_score(predicted, goal_weights)` — normalises and weights predicted values into a single 0–1 score
- `suggest_next_configurations(experiment)` — post-completion: suggests 3 next compositions to try

### `knowledge_graph.py`
NetworkX-backed directed graph built lazily from Qdrant data (TTL: 300s).

**Node types:** `material`, `property`, `document`, `condition`
**Edge types:** `HAS_PROPERTY`, `IMPROVES`, `DEGRADES`, `SIMILAR_TO`, `MEASURED_BY`, `CONTAINS`

Graph-enhanced search re-ranks results with:
```
final_score = 0.6 × vector_score + 0.3 × PageRank + 0.1 × connectivity
```
Falls back to pure vector search if NetworkX is not installed or graph build fails.

### `chat.py`
RAG chat engine. Three expert roles:

| Role ID | Persona |
|---|---|
| `material-expert` | Senior Materials Science Expert — detailed technical analysis, standards, grade comparisons |
| `technical-reviewer` | Technical Document Reviewer — QA, gaps, compliance, red flags |
| `literature-researcher` | Literature Researcher — paper synthesis, research gaps, methodology comparison |

`ChatSession` stores turns in memory and persists to `chat_sessions` Qdrant collection. Memory window: last **4 turns** (8 messages). Streaming via SSE — tokens arrive token-by-token in the browser.

### `crawler.py`
Recursive folder scanner. Deduplicates via SHA-256 hash comparison against `get_all_file_hashes()`. Supported extensions: `.pdf`, `.docx`, `.doc`. Queues each new file as a job.

### `startup.py`
One-time setup script — initialises all Qdrant collections with correct vector configs. Run manually if Qdrant is fresh.

### `bulk_parser.py`
CLI utility for batch-parsing a directory of PDFs outside the web UI — useful for initial corpus loading.

### `refresh_system.py`
Utility for rebuilding Qdrant collections from on-disk parsed JSON cache without re-running the LLM — fast re-index after schema changes.

---

## 5. Frontend Component Reference

All components are in `src/components/`. The app uses React 18 with no external state management library — prop drilling from `App.jsx` for loop/nav state, local `useState` for everything else.

### `App.jsx`
Root component. Owns:
- `activeNav` — current view (research / papers / experiments / results / decisions / chat)
- `sidebarCollapsed` — persisted in `localStorage`
- `loopState` — polled every 3 seconds from `/api/loop/status`
- `counts` — polled every 5 seconds from `/api/stats`

Renders six view layouts: `ResearchView`, `ExperimentsView`, `ResultsOnlyView`, `DecisionsView`, `ChatView`, and `PapersView`. Page transitions use a `view-transition` CSS animation class (0.22s `viewEnter` keyframe) wrapping each view.

### `Sidebar.jsx`
Collapsible navigation sidebar.
- Expanded width: `220px` | Collapsed width: `56px`
- CSS `width` transition (`0.25s cubic-bezier(0.4,0,0.2,1)`) — no JS animation
- Label text and badge counts hidden at collapsed state via `opacity: 0; width: 0; overflow: hidden`
- ChevronLeft/Right toggle button pinned to the right edge of the sidebar
- State persisted in `localStorage` via `App.jsx`
- System status row (Ollama / Qdrant / Engine) shows icons-only when collapsed, with `title` tooltip
- Keyboard navigation: ArrowUp/Down moves focus between nav items

### `GoalPanel.jsx`
Research goal input and loop control.
- Text area for research goal description
- Three weight sliders (Strength / Flexibility / Cost)
- Loop toggle (start/stop continuous loop) and single-iteration "Run Once" button
- Shows current loop status, iteration counter, and active step name

### `KnowledgePanel.jsx`
Displays the knowledge graph summary and recently indexed documents. Quick-access view into what the system currently knows.

### `ExperimentDashboard.jsx`
Compact experiment overview embedded in the Research view. Shows recent experiments with status and confidence scores. Clicking a row fires `onSelect` to populate `ResultsPanel`.

### `ExperimentsPanel.jsx`
Full experiments view — 3-column kanban board.

| Column | Statuses | Header colour |
|---|---|---|
| Queued | `pending`, `queued` | Muted grey |
| Running | `running` | Electric Indigo (`#6d6af8`) |
| Completed | `completed`, `failed` | Green / Red |

**`KanbanCard`** features:
- 3px status-coloured left border
- Experiment name (bold) + iteration badge (mono, top-right corner)
- Material name (mono, muted, ellipsis overflow)
- Confidence bar (100%, 3px tall) + percentage — only on completed/failed cards
- Running cards: `kanban-running-pulse` border animation (indigo cycling)
- Hover: `translateY(-2px)` + shadow lift
- Click: opens `ExperimentDetailModal`

**`ExperimentDetailModal`:**
- Full experiment details, conditions, expected output
- Test results table (metric / expected / actual / deviation / pass)
- Inline "Add Result" form
- AI Predict button (LLM property prediction with Qdrant context)
- Suggest button (post-completion — next 3 configurations)
- Complete button (marks experiment done and records actual output)
- Delete button with confirmation

### `ResultsPanel.jsx`
Comparative results analysis. Recharts bar and line charts. Shows predicted vs actual property values across iterations. Can be scoped to a selected experiment or show all.

### `DecisionPanel.jsx`
Shows the current loop state during autonomous operation:
- Active step progress bar (Retrieve → Generate → Evaluate → Decide → Approve)
- Current reasoning and hypothesis text (inline-editable)
- Candidate list with scores
- Approve / Stop loop buttons

### `PapersView.jsx`
Document library management.

**Stat bar (top):** Total Documents / TDS Count / Research Papers / Qdrant Points — rendered with `StatCard` (28px, weight 800 numbers in Electric Indigo, amber, green).

**Upload controls:**
- Single PDF upload via `POST /api/documents/upload`
- Folder upload (`<input webkitdirectory multiple accept=".pdf">`) — correctly passes all files in a selected directory on Windows Chrome
- URL/path scan (folder path input → `POST /api/folders/scan`)

**Documents table:**
- Checkbox column (per-row select + select-all header checkbox)
- Filename, type badge (TDS / Paper), status, properties extracted count, upload date
- Bulk delete button appears in panel header when any rows are selected (red styling, shows selected count)
- Row click → opens `DocumentDetails` modal

**Job queue panel:** Live list of ingestion jobs with status indicator, priority badge, elapsed time, and error messages.

### `DocumentDetails.jsx`
Full document inspection modal. Six tabs:

| Tab | Content |
|---|---|
| Overview | Extraction status, confidence score, doc type, property count |
| Properties | Table of all extracted property rows (name / value / unit / confidence / context) |
| Methodology | LLM-extracted research methodology text (papers only) |
| Key Findings | Bulleted list of extracted findings (papers only) |
| Limitations | Extracted limitations and caveats (papers only) |
| Raw Data | Full LLM JSON output for debugging |

**Re-extract button** — re-runs LLM extraction on the stored file. Always refreshes the UI regardless of whether new properties were found (previously had a conditional guard that blocked refresh).

Status field normalised: checks `extraction_status` first, falls back to `status`.

### `ChatPanel.jsx`
RAG-powered Q&A interface.
- Role selector (Material Expert / Technical Reviewer / Literature Researcher)
- Message history with user/assistant chat bubbles
- SSE streaming — response tokens appear incrementally as they arrive
- Clear chat button (resets session on backend)
- `Loader` spinner rendered during generation (previously missing from imports, causing a React render crash that blanked the entire screen on message send)

### `CyberLoader.jsx`
Loading screen shown on initial app startup while the backend connection is being established. Displays an animated progress bar.

---

## 6. Qdrant Schema — 8 Collections

All collections use **flat payloads** — no nested `metadata` key.

### `documents` — Document manifest

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | UUID, primary key |
| `filename` | string | Original filename |
| `file_path` | string | Absolute path on disk |
| `file_hash` | string | SHA-256 (for dedup) |
| `doc_type` | string | `"tds"` or `"paper"` |
| `extraction_status` | string | `pending / running / completed / failed` |
| `material_name` | string | Extracted material name |
| `properties_extracted` | int | Count of property rows |
| `extraction_confidence` | float | 0.0–1.0 |
| `methodology` | string | Extracted research methodology (papers) |
| `research_objective` | string | Extracted research objective (papers) |
| `key_findings` | JSON string | List of key findings (papers) |
| `processing_conditions` | JSON string | List of processing conditions |
| `created_at` | ISO datetime | — |
| `updated_at` | ISO datetime | — |

Vector: 768-dim embedding of `filename + material_name`.

### `doc_chunks` — Text chunks (primary search target)

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Parent document ID |
| `chunk_index` | int | Position in document |
| `content` | string | 2000-char text chunk |
| `filename` | string | Parent filename |
| `doc_type` | string | Inherited from parent |

Vector: 768-dim `nomic-embed-text` embedding of `content`. This is the collection searched during RAG.

### `material_properties` — Structured property rows

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Parent document |
| `property_name` | string | e.g. "Tensile Strength" |
| `value` | any | Numeric or string |
| `unit` | string | e.g. "MPa" |
| `confidence` | float | LLM extraction confidence |
| `context` | string | Test standard or note |

### `experiments` — Autonomous loop results

| Field | Type | Description |
|---|---|---|
| `experiment_id` | string | UUID |
| `name` | string | Human-readable name |
| `material_name` | string | Target material |
| `status` | string | `pending / running / completed / failed` |
| `conditions` | JSON | `{temperature, pressure, time}` |
| `expected_output` | JSON | `{tensile_strength, elongation}` |
| `actual_output` | JSON | Recorded measurements |
| `results` | JSON | List of `{metric, expected, actual, deviation, passed}` |
| `confidence` | float | Composite score (0–1) |
| `iteration` | int | Loop iteration number |
| `created_at` | ISO datetime | — |

### `knowledge_edges` — Graph edges

| Field | Type | Description |
|---|---|---|
| `source` | string | Source node ID |
| `target` | string | Target node ID |
| `edge_type` | string | `HAS_PROPERTY / IMPROVES / DEGRADES / SIMILAR_TO / MEASURED_BY / CONTAINS` |
| `weight` | float | Edge strength |

### `scanned_folders` — Folder registry

Tracks which local paths have been scanned to avoid re-scanning. Uses a 1-dim dummy vector.

### `job_status` — Ingestion job tracking

| Field | Type | Description |
|---|---|---|
| `job_id` | string | UUID |
| `filename` | string | — |
| `status` | string | `pending / queued / running / completed / failed / cancelled` |
| `priority` | string | `HIGH / MEDIUM / LOW` |
| `file_size` | int | Bytes |
| `error` | string | Error message if failed |
| `created_at` | ISO datetime | — |
| `completed_at` | ISO datetime | — |

### `chat_sessions` — Conversation history

| Field | Type | Description |
|---|---|---|
| `session_id` | string | UUID |
| `messages` | JSON | List of `{role, content, timestamp}` |
| `created_at` | ISO datetime | — |

---

## 7. Data & Ingestion Pipeline

### File types supported
- `.pdf` — primary target (pdfplumber + PyPDF2 fallback)
- `.docx`, `.doc` — supported by crawler, not yet wired to the direct upload endpoint

### Deduplication
SHA-256 hash of file content, checked against all hashes in `documents` collection before queuing. Duplicate uploads are rejected silently at the crawler level.

### Chunking strategy
- Chunk size: **2000 characters** (~512 tokens at 4 chars/token)
- Overlap: **200 characters**
- Each chunk is embedded independently with `nomic-embed-text`

### LLM extraction
The LLM receives the first ~8000 characters of the document (truncated to stay inside the effective context window for fast inference on 14b models). It is instructed to return strict JSON only — no markdown, no explanation. Malformed JSON triggers a retry with a simplified prompt.

### Priority queue
Jobs are inserted into a min-heap keyed on `(priority.value, created_at)`. A single daemon thread processes one job at a time. The worker is started on FastAPI startup and runs until the process exits.

---

## 8. Autonomous Research Loop

The loop is the core differentiator of this platform — it closes the hypothesis–experiment–result cycle with minimal human intervention.

### State machine

```
        ┌─────────────────────────────────────────────┐
        │                    IDLE                      │
        └──────────────────────┬──────────────────────┘
                               │ start_loop(goal, weights)
        ┌──────────────────────▼──────────────────────┐
        │                   RUNNING                    │
        │  Step 1: Retrieve (Qdrant RAG context)       │
        │  Step 2: Generate (LLM hypothesis)           │
        │  Step 3: Evaluate (predict + score)          │
        │  Step 4: Decide   (pick best candidate)      │
        └──────────────────────┬──────────────────────┘
                               │ iteration complete
        ┌──────────────────────▼──────────────────────┐
        │              AWAITING_APPROVAL               │
        │  Shows reasoning, candidates, scores to user │
        └──────┬──────────────────────────────┬───────┘
               │ approve()                    │ stop()
        ┌──────▼──────┐                ┌──────▼──────┐
        │   RUNNING   │                │   STOPPED   │
        │ (next iter) │                └─────────────┘
        └─────────────┘
```

### Loop iteration detail

1. **Retrieve** — `qdrant_mgr.search(goal)` pulls top-5 most relevant doc chunks as LLM context
2. **Generate** — LLM is given the goal, current best score, iteration history, and Qdrant context; outputs a hypothesis (material + composition + conditions)
3. **Evaluate** — `predict_properties()` predicts tensile strength, elongation, modulus from the hypothesis using Qdrant context
4. **Decide** — `calculate_composite_score()` scores prediction against goal weights; picks best from 3 candidates
5. **Approve** — loop pauses at `AWAITING_APPROVAL`; user reviews in `DecisionPanel`; can edit the next hypothesis before approving

### Composite score formula
```
score = (strength_value × w_strength) + (flexibility_value × w_flexibility) + (cost_factor × w_cost)
```
Default weights: `0.50 / 0.35 / 0.15`. User-configurable in `GoalPanel`.

### Human-in-the-loop controls
- **Approve** — accept the current decision and proceed to next iteration
- **Edit hypothesis** — modify the LLM-generated text before it is run
- **Stop** — halt the loop (state is preserved in memory for the session)
- **Run Once** — run a single iteration without entering continuous mode

---

## 9. Chat System

Every user question is answered in the context of the local document library — no general internet access.

### Retrieval
1. Embed user query with `nomic-embed-text`
2. Cosine search on `doc_chunks` collection (top 5 chunks)
3. Optionally expand via knowledge graph (2-hop PageRank, when NetworkX is available)
4. Re-rank: `0.6 × vector_score + 0.3 × PageRank + 0.1 × connectivity`

### Roles

| Role | Focus |
|---|---|
| Material Expert | Technical property analysis, standards (ISO/ASTM/UL), grade comparisons, alternative materials |
| Technical Reviewer | QA, compliance gaps, inconsistencies, red flags in property data |
| Literature Researcher | Paper synthesis, key findings summary, methodology comparison, research gaps |

### Memory
- Last **4 turns** (8 messages) retained in the LLM context window
- Full session persisted to `chat_sessions` Qdrant collection between browser refreshes
- Session ID is stable for the duration of the browser session

### Streaming
Responses are streamed token-by-token via Server-Sent Events (SSE). The browser renders each token as it arrives — no waiting for the complete response.

---

## 10. API Reference

All routes are at `http://localhost:8000`.

### Documents
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Upload single PDF |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Get document with full payload |
| `DELETE` | `/api/documents/{id}` | Delete single document |
| `POST` | `/api/documents/bulk-delete` | Delete list of IDs (JSON array body) |
| `POST` | `/api/documents/{id}/reprocess` | Re-run LLM extraction |

### Jobs
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}` | Get single job |
| `GET` | `/api/jobs/{id}/stream` | SSE job progress stream |
| `DELETE` | `/api/jobs/{id}` | Cancel job |

### Experiments
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/experiments` | List experiments |
| `POST` | `/api/experiments` | Create experiment |
| `GET` | `/api/experiments/{id}` | Get experiment detail |
| `DELETE` | `/api/experiments/{id}` | Delete experiment |
| `POST` | `/api/experiments/{id}/results` | Add test results |
| `POST` | `/api/experiments/{id}/predict` | LLM property prediction |
| `POST` | `/api/experiments/{id}/suggest` | Next config suggestions |
| `POST` | `/api/experiments/{id}/complete` | Mark completed |

### Research Loop
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/loop/status` | Current loop state |
| `POST` | `/api/loop/start` | Start/reset loop |
| `POST` | `/api/loop/iterate` | Run single iteration |
| `POST` | `/api/loop/approve` | Approve + continue |
| `POST` | `/api/loop/stop` | Stop loop |
| `PUT` | `/api/loop/hypothesis` | Edit pending hypothesis text |

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Send message (returns SSE stream) |
| `GET` | `/api/chat/sessions` | List sessions |
| `DELETE` | `/api/chat/sessions/{id}` | Clear session history |

### System
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Ollama + Qdrant connectivity check |
| `GET` | `/api/stats` | Document/experiment/chunk counts |
| `POST` | `/api/folders/scan` | Trigger recursive folder crawl |

---

## 11. Project Phases

### Phase 1 — Core Ingestion Pipeline ✅ Complete

**Goal:** Get PDFs in, properties out, stored in Qdrant.

- [x] FastAPI backend skeleton (`main.py`, `config.py`)
- [x] PDF text extraction (`parser.py` — pdfplumber + PyPDF2 fallback)
- [x] LLM property extraction (`extractor.py` — TDS schema + Paper schema)
- [x] Qdrant storage layer (`qdrant_store.py` — 8 collections designed and initialised)
- [x] Background job queue with priority tiers by file size (`job_queue.py`)
- [x] Job status persistence to Qdrant — survives backend restarts
- [x] SHA-256 deduplication at crawl time
- [x] Single PDF upload endpoint
- [x] Folder scan endpoint (`crawler.py` — recursive, dedup-aware)
- [x] `GET /api/documents` + `GET /api/documents/{id}` endpoints
- [x] React frontend scaffolded (Vite + Tauri shell)
- [x] `PapersView` — upload UI, job queue panel, documents table

---

### Phase 2 — Research Loop & Experiments ✅ Complete

**Goal:** Close the hypothesis → experiment → result cycle autonomously.

- [x] Autonomous loop orchestrator (`orchestrator.py` — `idle / running / awaiting_approval / stopped` state machine)
- [x] Experiment runner with LLM prediction and composite scoring (`experiment_runner.py`)
- [x] Knowledge graph (`knowledge_graph.py` — NetworkX over Qdrant edges, 300s TTL cache)
- [x] Graph-enhanced search (vector + PageRank + connectivity re-rank)
- [x] `GoalPanel` — goal text input + weight sliders (Strength / Flexibility / Cost) + loop controls
- [x] `DecisionPanel` — step progress bar + approve/stop + inline hypothesis edit
- [x] `ExperimentDashboard` — compact experiment overview in Research view
- [x] `ExperimentsPanel` — full experiments CRUD with create, view, add results, predict, suggest, complete, delete
- [x] `ResultsPanel` — Recharts comparative visualisation (predicted vs actual)
- [x] Human-in-the-loop approval gate (`AWAITING_APPROVAL` state)

---

### Phase 3 — Chat & Knowledge Inspection ✅ Complete

**Goal:** Make the knowledge base queryable in plain language.

- [x] RAG chat engine (`chat.py` — LangChain + Qdrant + role system)
- [x] Three expert roles with distinct system prompts
- [x] SSE streaming responses — token-by-token delivery
- [x] Session memory persisted to Qdrant `chat_sessions` collection
- [x] `ChatPanel` — role selector, message history, streaming bubbles
- [x] `KnowledgePanel` — graph summary view
- [x] `DocumentDetails` modal — all tabs (Overview / Properties / Methodology / Key Findings / Limitations / Raw Data)
- [x] Re-extraction (reprocess) flow — always refreshes UI regardless of result count
- [x] `methodology`, `key_findings`, `processing_conditions`, `research_objective` fields extracted and stored in document manifest

---

### Phase 4 — Bug Fixes & Data Quality ✅ Complete

**Goal:** Fix all known data pipeline and UI bugs discovered during internal testing.

- [x] **Folder upload single-file bug** — `webkitdirectory` without `multiple` on Windows Chrome passed only the first file. Fixed by adding `multiple` attribute to the folder input.
- [x] **Chat screen goes blank on send** — `Loader` component was used in `ChatPanel.jsx` but never imported. React render crashed silently when `loading=true`. Fixed by adding `Loader` to the lucide-react import.
- [x] **Re-extract button no visible change** — three separate bugs: (1) conditional `if properties_extracted > 0` guard blocked refresh on empty results, (2) `extraction_status` vs `status` field name mismatch, (3) `llm_output` was never set in the non-Qdrant fetch path. All three fixed.
- [x] **Methodology / findings / limitations not showing** — `upsert_document()` had no fields for these; `process_job()` never passed them. Fixed by extending both `upsert_document()` and `update_document_properties_count()` with all four research fields, and passing them from `process_job()`.
- [x] **Bulk delete** — added `DELETE /api/documents/{id}` and `POST /api/documents/bulk-delete` endpoints. Added checkbox column with select-all to `PapersView` table; bulk delete button appears in header when rows are selected.

---

### Phase 5 — UI/UX Overhaul ✅ Complete

**Goal:** Shift from sterile green palette to a modern, premium research tool aesthetic that feels alive rather than clinical.

- [x] **Electric Indigo palette** — full `:root` token swap in `index.css`
  - Primary accent: `#6d6af8` (Electric Indigo)
  - Secondary accent: `#e8962a` (Warm Amber)
  - Base background: `#07090f`
  - Glass background: `rgba(13,18,32,0.60)` + `blur(20px)`
  - Success/score-high states retain green (`#4db882`) — green means good, indigo means active
  - Error/score-low shifted to `#e05555` (brighter, more legible)
- [x] **Radial gradient body background** — subtle indigo ellipse at top-left + amber ellipse at bottom-right, gives depth without distraction
- [x] **Heavy glassmorphism on panels** — `backdrop-filter: blur(20px)`, `box-shadow: 0 4px 24px rgba(0,0,0,0.4)`, 1px inset top-edge highlight (depth, not glow)
- [x] **Frosted topbar** — `rgba(7,9,15,0.75)` background + `blur(20px)`, visually elevated above the workspace
- [x] **Collapsible sidebar**
  - CSS width transition: `0.25s cubic-bezier(0.4,0,0.2,1)`
  - Expanded: `220px` / Collapsed: `56px`
  - Label text, badges, logo text: `opacity: 0; width: 0; overflow: hidden` at collapsed state (smooth transition, not display:none)
  - ChevronLeft / ChevronRight toggle button on the right edge
  - State persisted in `localStorage` — survives page refresh
  - Tooltips via `title` attribute on each nav item at collapsed state
  - Expanded by default
- [x] **Sidebar nav hover** — icon slides `2px` to the right on hover
- [x] **Page transition animations** — `viewEnter` keyframe (0.22s fade+slide) on `activeNav` change. Wrapper uses `display: contents` to avoid adding a flex layer.
- [x] **Stat card numbers** — `28px`, `font-weight: 800` (up from `12px`)
- [x] **Topbar title** — `18px`, `font-weight: 700`
- [x] **Experiments Kanban board** — 3-column layout replacing the flat card list
  - `KanbanColumn` component: glass panel header with colour-coded title + count pill, independently scrollable body
  - `KanbanCard`: 3px status-coloured left border, name + iter badge, material name (mono/muted), confidence bar for completed/failed, running pulse animation
  - Column assignment: Queued (`pending`/`queued`), Running (`running`), Completed (`completed`/`failed`)
  - Header bar: search input + total count + "New" button in one row (replaces the previous two-row controls block)

---

### Phase 6 — Chat Enhancement 🔲 Pending

**Goal:** Upgrade chat from basic local RAG to a fully-capable research assistant with web awareness and better conversational intelligence.

- [ ] **DuckDuckGo web search** (`backend/web_search.py`) — triggered on three tiers:
  1. Explicit commands: `"search for..."`, `"look up..."`, `"find online..."`
  2. Recency/live intent: `"latest"`, `"2024"`, `"recent developments"`, `"current"`
  3. Discovery cues: `"find papers on"`, `"what is X"`, `"who invented"`
- [ ] **Combined retrieval** — merge local Qdrant results + web results, deduplicate by content similarity, unified re-rank
- [ ] **Query rephrasing before retrieval** — LLM resolves pronouns and implicit references in follow-up questions before the Qdrant search (e.g. `"what about its elongation?"` → `"EPDM rubber elongation at break"`)
- [ ] **`<thinking>` tag stripping** — remove chain-of-thought XML tags from LLM output before streaming to the browser
- [ ] **Memory window expansion** — 4 turns → 10 turns
- [ ] **Two additional roles**:
  - Document Parser — extraction quality review, JSON output inspection
  - Document Analyst — cross-document comparison and contradiction detection
- [ ] **Source citations in chat** — show which filenames/chunk positions each response drew from

---

### Phase 7 — Orchestrator Intelligence 🔲 Pending

**Goal:** Replace the placeholder loop logic with genuinely intelligent hypothesis generation grounded in the knowledge base.

- [ ] **Real LLM-driven hypothesis generation** — LLM reads current best experiment, full iteration history, and Qdrant context to generate a specific, justified next configuration (not random perturbation of previous values)
- [ ] **Multi-candidate generation** — generate 5 candidates per iteration, score all, present top 3 with reasoning to user
- [ ] **Iteration memory in LLM context** — full loop history (all hypotheses, scores, and outcomes) available to the LLM at each step
- [ ] **Goal decomposition** — LLM breaks high-level research goal into sub-goals; tracks progress against each sub-goal across iterations
- [ ] **Automatic result ingestion** — if an experiment result PDF is uploaded, parse it and automatically feed results back into the relevant experiment record without the manual "Add Result" step
- [ ] **Loop history export** — export complete decision log (goal → hypotheses → scores → approvals → outcomes) as a structured PDF or JSON report

---

### Phase 8 — Multi-Model Routing 🔲 Pending

**Goal:** Use the right model for each task rather than routing everything through one model.

- [ ] **Orchestrator** — `qwen2.5:14b` for hypothesis generation (reasoning-intensive)
- [ ] **Property extraction** — `qwen2.5:7b` for speed on structured JSON tasks
- [ ] **Chat roles** — smaller models for structured reviewer tasks, larger for open-ended expert analysis
- [ ] **Embedding alternatives** — evaluate `bge-m3` (multilingual) and `mxbai-embed-large` (higher accuracy) as alternatives to `nomic-embed-text`
- [ ] **Settings panel** — hot-swap model selection in the UI without restarting the backend; model health check per-task

---

### Phase 9 — Desktop Application 🔲 Pending

**Goal:** Package as a zero-install standalone desktop app for internal lab distribution.

- [ ] **Tauri desktop shell** — Tauri is already scaffolded in the project (`@tauri-apps/cli` present); activate native window wrapper and system tray
- [ ] **Auto-start backend** — Tauri sidecar launches FastAPI + Uvicorn on app open; graceful shutdown on close
- [ ] **Auto-start Ollama** — check if Ollama is running; launch as a managed child process if not
- [ ] **Bundled Qdrant** — embed Qdrant binary, launch on startup, shutdown on exit; no separate Qdrant install required for end users
- [ ] **Windows installer** — NSIS-based `.exe` with all dependencies bundled
- [ ] **First-run setup wizard** — model download progress, Qdrant initialisation, single test document ingestion to verify the pipeline
- [ ] **Auto-update** — Tauri updater plugin pointing to internal release server for silent updates

---

## 12. Setup & Running

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Backend runtime |
| Node.js 18+ | Frontend build |
| Ollama | Download from ollama.com; CUDA drivers recommended |
| Qdrant | Run locally on port 6333 |
| NVIDIA GPU | Optional but strongly recommended; CPU inference on 14b is very slow |

### 1. Start Qdrant

```bash
# Docker (recommended)
docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant

# Or Qdrant binary directly on Windows
qdrant.exe
```

### 2. Pull Ollama models

```bash
ollama pull qwen2.5:14b-instruct-q4_K_S
ollama pull nomic-embed-text
```

### 3. Start the backend

```bash
cd backend
pip install -r requirements.txt
python main.py
# Listening on http://localhost:8000
```

### 4. Start the frontend

```bash
# Project root
npm install
npm run dev
# Opens http://localhost:5173
```

### First-time Qdrant initialisation

If Qdrant is freshly installed and collections do not exist yet:

```bash
cd backend
python startup.py
```

---

## 13. Directory Structure

```
rlresearchassistant/
├── backend/
│   ├── main.py               # FastAPI app + all API routes
│   ├── config.py             # All constants (URLs, models, paths, collection names)
│   ├── parser.py             # PDF → raw text (pdfplumber + PyPDF2)
│   ├── extractor.py          # LLM property extraction (TDS + Paper schemas)
│   ├── llm.py                # Ollama client wrapper
│   ├── qdrant_store.py       # Storage abstraction (all 8 collections)
│   ├── qdrant_mgr.py         # Higher-level search wrapper for RAG
│   ├── job_queue.py          # Priority queue + background worker
│   ├── orchestrator.py       # Autonomous loop state machine
│   ├── experiment_runner.py  # LLM property prediction + composite scoring
│   ├── knowledge_graph.py    # NetworkX graph over Qdrant edges
│   ├── chat.py               # RAG chat engine + role system + session memory
│   ├── crawler.py            # Recursive folder scanner with dedup
│   ├── startup.py            # One-time Qdrant collection initialisation
│   ├── bulk_parser.py        # CLI batch parser utility
│   ├── refresh_system.py     # Re-index from cached JSON without re-running LLM
│   ├── db.py                 # Legacy SQLite stub (unused, kept for import compat)
│   └── data/
│       ├── uploads/          # Temp upload staging area
│       ├── parsed/           # Cached extracted JSON (for refresh_system.py)
│       └── qdrant_storage/   # Qdrant on-disk vector storage
│
├── src/
│   ├── App.jsx               # Root — routing, loop state, sidebar collapse state
│   ├── index.css             # Full design system (CSS tokens, components, animations)
│   └── components/
│       ├── Sidebar.jsx           # Collapsible navigation sidebar
│       ├── GoalPanel.jsx         # Research goal + weight sliders + loop controls
│       ├── KnowledgePanel.jsx    # Knowledge graph summary panel
│       ├── ExperimentDashboard.jsx  # Compact experiments summary (Research view)
│       ├── ExperimentsPanel.jsx  # 3-column kanban board + modals
│       ├── ResultsPanel.jsx      # Recharts comparative visualisation
│       ├── DecisionPanel.jsx     # Loop step progress + approve + hypothesis edit
│       ├── PapersView.jsx        # Document library, upload, bulk operations
│       ├── DocumentDetails.jsx   # Document inspection modal (6 tabs)
│       ├── ChatPanel.jsx         # RAG chat with role selector and SSE streaming
│       └── CyberLoader.jsx       # Animated startup loading screen
│
├── public/
│   └── favicon.svg
├── dist/                     # Vite production build output
├── vite.config.js
├── package.json
└── README.md
```

---

## 14. Known Limitations & Design Decisions

### LLM context window truncation
The extractor sends only the first ~8000 characters of a document to the LLM. TDS documents longer than ~20 pages may have properties on later pages that are missed entirely. A chunked extraction strategy (process each chunk separately, then merge results) is planned for Phase 7.

### Scanned-only PDFs
No OCR is implemented. PDFs that are image-only (no text layer) will produce empty extraction results. `parser.py` logs a warning but does not fail the job — the document is indexed as a manifest with zero properties.

### Single background worker
One worker thread processes one document at a time. This is intentional — the RTX 3050 has 4GB VRAM, and running two LLM inference jobs simultaneously would cause OOM errors. Parallel extraction requires model offloading or a larger GPU.

### Chat session identity
Chat sessions are identified by a client-generated UUID stored in React component state. If the browser tab is refreshed without persisting the session ID to `localStorage`, the active history is inaccessible (though still stored in Qdrant). A proper `localStorage`-backed session ID is a pending improvement.

### Knowledge graph rebuild latency
The NetworkX graph is rebuilt from Qdrant every 300 seconds (5 minutes). Heavy document ingestion during a session means the graph may lag behind the actual collection state by up to 5 minutes. The TTL is configurable in `config.py`.

### No authentication layer
The platform has no authentication or authorisation. It is designed exclusively for single-user, local-network deployment. Exposing port 8000 to a wider network without adding an auth layer (e.g. OAuth2 + JWT via FastAPI's security utilities) would be a security risk.

### LLM non-determinism in extraction
Property extraction results can vary slightly between re-extraction runs on the same document. Temperature is set to 0 for extraction tasks, but GGUF runtime inference introduces minor sampling variance at low temperatures. Confidence scores should be treated as approximate indicators, not precise measurements.

### `db.py` / SQLite legacy
An early prototype of this platform used SQLite (`research.db`) for all storage. It was replaced entirely by Qdrant. `db.py` remains in the codebase only because removing it would require auditing all imports. Nothing writes to `research.db`. It will be removed in a future cleanup pass.

### Tauri shell is dormant
`@tauri-apps/cli` and `@tauri-apps/plugin-shell` are in `package.json`, and a `src-tauri/` directory exists. The Tauri shell is not yet activated — the app runs purely as a browser-based Vite dev server. Activating the desktop shell is Phase 9.
