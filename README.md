# MatResOps — AI Materials Research Operator

> **Planet Material Labs** · Autonomous Closed-Loop Experimentation Platform  
> *A local-first, AI-powered system for polymer & composites science research*

---

## Table of Contents

1. [Vision](#1-vision)
2. [Architecture Overview](#2-architecture-overview)
3. [System Requirements](#3-system-requirements)
4. [Tech Stack Deep Dive](#4-tech-stack-deep-dive)
5. [Application UI — Panel by Panel](#5-application-ui--panel-by-panel)
6. [Data Architecture](#6-data-architecture)
7. [The Autonomous Loop — State Machine](#7-the-autonomous-loop--state-machine)
8. [API Reference](#8-api-reference)
9. [Codebase Map](#9-codebase-map)
10. [Sprint Plan — Progress Tracker](#10-sprint-plan--progress-tracker)
11. [Running the System](#11-running-the-system)
12. [Known Issues & Limitations](#12-known-issues--limitations)
13. [Roadmap — What's Left](#13-roadmap--whats-left)

---

## 1. Vision

MatResOps is a **closed-loop autonomous experimentation system** for polymer and materials science. A researcher sets a natural-language goal — the system does the rest: retrieves relevant knowledge, generates formulation candidates, scores them using heuristic + LLM engines, selects the best, explains *why*, proposes the next hypothesis, and loops — pausing at each iteration for human approval.

```
  "Maximize tensile strength (>45 MPa) while keeping elongation >180%
   and minimizing cost. Prefer bio-based additives."
                              │
                              ▼
         ┌────────────────────────────────────┐
         │         MATRESOPS ENGINE           │
         │                                    │
         │  retrieve → generate → evaluate    │
         │     → decide → approve → repeat    │
         └────────────────────────────────────┘
                              │
                              ▼
         "Iteration 4 winner: Config B (0.847)
          EPDM 75% + Silica 12% + Plasticizer 8%
          Next: reduce plasticizer to 6%, add
          cross-linker at 2% to recover tensile."
```

**What makes this different from ChatGPT / NotebookLM / Elicit:**

| Feature                    | MatResOps | NotebookLM | Elicit | ChatGPT |
|----------------------------|:---------:|:----------:|:------:|:-------:|
| Fully local / offline      | ✅        | ❌         | ❌     | ❌      |
| Active experiment loop     | ✅        | ❌         | ❌     | ❌      |
| TDS structured extraction  | ✅        | ❌         | ⚠️    | ⚠️     |
| Heuristic scoring engine   | ✅        | ❌         | ❌     | ❌      |
| Typed decision reasoning   | ✅        | ❌         | ⚠️    | ❌      |
| Autonomous iteration       | ✅        | ❌         | ❌     | ❌      |
| 14,000 TDS batch pipeline  | ✅        | ❌         | ❌     | ❌      |

---

## 2. Architecture Overview

### 2.1 High-Level System Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          MATRESOPS — PLANET MATERIAL LABS                       ║
║                                                                                  ║
║  ┌─────────────────────────────────────────────────────────────────────────┐    ║
║  │                     TAURI v2 DESKTOP SHELL (Rust)                        │    ║
║  │                                                                          │    ║
║  │   ┌──────────┐  ┌──────────────────────────────────────────────────┐    │    ║
║  │   │ SIDEBAR  │  │          REACT + VITE WORKSPACE (18.3)           │    │    ║
║  │   │          │  │                                                  │    │    ║
║  │   │ Research │  │  ┌──────────────┐  ┌───────────────────────┐    │    │    ║
║  │   │ Papers   │  │  │ GOAL PANEL   │  │ KNOWLEDGE VIEW        │    │    │    ║
║  │   │ Exprmts  │  │  │              │  │                       │    │    │    ║
║  │   │ Results  │  │  │ Textarea     │  │ Papers · TDS cards    │    │    │    ║
║  │   │ Decision │  │  │ Weight sliders│  │ Insight chips        │    │    │    ║
║  │   │ Chat     │  │  │ Start Loop ▶ │  │ Semantic search       │    │    │    ║
║  │   │          │  │  └──────────────┘  └───────────────────────┘    │    │    ║
║  │   │ ● Ollama │  │                                                  │    │    ║
║  │   │ ● Qdrant │  │  ┌────────────────────┐  ┌──────────────────┐  │    │    ║
║  │   │ ● DuckDB │  │  │ EXPERIMENT DASHBOARD│  │ DECISION PANEL   │  │    │    ║
║  │   └──────────┘  │  │                    │  │                  │  │    │    ║
║  │                  │  │ 🏆 Config A 0.847 ▓│  │ 🧠 Reasoning... │  │    │    ║
║  │                  │  │    Config B 0.731 ▒│  │ Typewriter anim │  │    │    ║
║  │                  │  │    Config C 0.612 ░│  │ 🔬 Next Hyp.    │  │    │    ║
║  │                  │  │                    │  │ [Approve ✓]     │  │    │    ║
║  │                  │  └────────────────────┘  └──────────────────┘  │    │    ║
║  │                  │                                                  │    │    ║
║  │                  │  ┌──────────────────────────────────────────┐   │    │    ║
║  │                  │  │         RESULTS VISUALIZATION             │   │    │    ║
║  │                  │  │  Radar Chart · Trend Line · Comparisons  │   │    │    ║
║  │                  │  └──────────────────────────────────────────┘   │    │    ║
║  │                  └──────────────────────────────────────────────────┘   │    ║
║  └─────────────────────────────────────────────────────────────────────────┘    ║
║                                    │                                             ║
║                        HTTP/REST (localhost:8000)                                ║
║                                    │                                             ║
║  ┌─────────────────────────────────▼────────────────────────────────────────┐   ║
║  │                    FASTAPI PYTHON BACKEND (v0.109)                        │   ║
║  │                                                                           │   ║
║  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │   ║
║  │  │ ORCHESTRATOR│  │ EXPERIMENT   │  │    CHAT     │  │  JOB QUEUE    │  │   ║
║  │  │             │  │   RUNNER     │  │             │  │               │  │   ║
║  │  │ State machine│  │ predict_    │  │ RAG + 3     │  │ Priority queue│  │   ║
║  │  │ idle→running │  │ properties()│  │ role personas│  │ Background    │  │   ║
║  │  │ →approval   │  │ score()     │  │ Session mem │  │ worker thread │  │   ║
║  │  │ →loop       │  │ suggest()   │  │ SSE support │  │ SHA-256 dedup │  │   ║
║  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘  │   ║
║  │         │                │                 │                 │           │   ║
║  │  ┌──────┴────────────────┴─────────────────┴─────────────────┴───────┐  │   ║
║  │  │                      DATA LAYER                                    │  │   ║
║  │  │                                                                    │  │   ║
║  │  │   ┌─────────────────────┐      ┌──────────────────────────────┐   │  │   ║
║  │  │   │   QDRANT (Docker)   │      │      DUCKDB (Embedded)       │   │  │   ║
║  │  │   │                     │      │                              │   │  │   ║
║  │  │   │ parsed_materials     │      │ documents  │ chunks          │   │  │   ║
║  │  │   │  768-dim vectors     │      │ material_  │ experiments     │   │  │   ║
║  │  │   │  22+ embeddings      │      │ properties │ experiment_     │   │  │   ║
║  │  │   │  Cosine similarity   │      │ extraction │ results         │   │  │   ║
║  │  │   │                     │      │ _data      │ decisions       │   │  │   ║
║  │  │   │ job_status          │      └──────────────────────────────┘   │  │   ║
║  │  │   │  1-dim job tracking │                                          │  │   ║
║  │  │   └─────────────────────┘                                          │  │   ║
║  │  └────────────────────────────────────────────────────────────────────┘  │   ║
║  └──────────────────────────────────────────────────────────────────────────┘   ║
║                                    │                                             ║
║                        Ollama HTTP API (localhost:11434)                         ║
║                                    │                                             ║
║  ┌─────────────────────────────────▼────────────────────────────────────────┐   ║
║  │                         OLLAMA LOCAL INFERENCE                            │   ║
║  │                                                                           │   ║
║  │   ┌────────────────────────────┐   ┌────────────────────────────────┐   │   ║
║  │   │  qwen2.5:14b-instruct      │   │  nomic-embed-text:latest       │   │   ║
║  │   │  (LLM generation)          │   │  (text embeddings, 768-dim)    │   │   ║
║  │   │  ~8GB RAM + partial GPU    │   │  ~274MB VRAM, full GPU         │   │   ║
║  │   │  15–45s per response       │   │  <500ms per embed              │   │   ║
║  │   └────────────────────────────┘   └────────────────────────────────┘   │   ║
║  └──────────────────────────────────────────────────────────────────────────┘   ║
║                                                                                  ║
║  Hardware: Intel Core i5 · NVIDIA RTX 3050 4GB VRAM · 32GB DDR4 RAM            ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

### 2.2 Document Ingestion Pipeline

```
  PDF / DOCX / DOC
        │
        ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                    INGESTION PIPELINE                            │
  │                                                                  │
  │  ┌──────────────┐     ┌─────────────────┐                       │
  │  │ FILE WATCHER │────▶│  JOB QUEUE      │                       │
  │  │              │     │  (job_queue.py)  │                       │
  │  │ Upload UI    │     │                  │                       │
  │  │ Folder scan  │     │  Priority:       │                       │
  │  │ SHA-256 dedup│     │  HIGH  <100KB    │                       │
  │  └──────────────┘     │  MEDIUM 100-500K │                       │
  │                        │  LOW   >500KB    │                       │
  │                        └────────┬─────────┘                       │
  │                                 │                                  │
  │                        ┌────────▼─────────┐                       │
  │                        │  BACKGROUND      │                       │
  │                        │  WORKER THREAD   │                       │
  │                        └────────┬─────────┘                       │
  │                                 │                                  │
  │              ┌──────────────────┼───────────────┐                 │
  │              ▼                  ▼               ▼                 │
  │  ┌────────────────┐  ┌──────────────────┐  ┌──────────────┐     │
  │  │  TEXT EXTRACT  │  │  TYPE DETECTION   │  │ LLM EXTRACT  │     │
  │  │  (pdfplumber / │  │                  │  │              │     │
  │  │   PyMuPDF)     │  │  TDS indicators: │  │  TDS schema: │     │
  │  │                │  │  "tensile"       │  │  {property,  │     │
  │  │  Tables → rows │  │  "ASTM", "shore" │  │   value,     │     │
  │  │  Text → paras  │  │  "mold temp"     │  │   unit,      │     │
  │  └────────┬───────┘  │                  │  │   confidence}│     │
  │           │           │  Paper indics:   │  │              │     │
  │           │           │  "abstract"      │  │  Paper schema│     │
  │           │           │  "doi:", "et al."│  │  {cause,     │     │
  │           │           └──────────────────┘  │   effect,    │     │
  │           │                                  │   magnitude} │     │
  │           │                                  └──────┬───────┘     │
  │           │                                         │              │
  │           ▼                                         ▼              │
  │  ┌──────────────────────────────────────────────────────────┐    │
  │  │              STORAGE (PARALLEL WRITE)                     │    │
  │  │                                                           │    │
  │  │  nomic-embed-text                                         │    │
  │  │  (768-dim vector)                                         │    │
  │  │        │                         │                        │    │
  │  │        ▼                         ▼                        │    │
  │  │  ┌───────────┐            ┌────────────────┐             │    │
  │  │  │  QDRANT   │            │    DUCKDB      │             │    │
  │  │  │ Semantic  │            │  Structured    │             │    │
  │  │  │ vector    │            │  properties    │             │    │
  │  │  │ search    │            │  relational    │             │    │
  │  │  └───────────┘            │  analytics     │             │    │
  │  │                           └────────────────┘             │    │
  │  └──────────────────────────────────────────────────────────┘    │
  └─────────────────────────────────────────────────────────────────┘
```

---

## 3. System Requirements

### 3.1 Current Development Machine

| Component     | Spec                                  | Role                              |
|---------------|---------------------------------------|-----------------------------------|
| **CPU**       | Intel Core i5 (gen unknown)           | Python backend, Ollama CPU layers |
| **GPU**       | NVIDIA RTX 3050 4GB VRAM             | LLM GPU layers, embeddings        |
| **RAM**       | 32GB DDR4                             | Ollama model overflow, DuckDB     |
| **OS**        | Windows 11 Home Single Language 10.0.26200 | Host                        |
| **Storage**   | SSD (recommended for 14K TDS files)  | ~20GB for full corpus + models    |

### 3.2 Software Dependencies

| Software          | Version         | Purpose                          | Install                          |
|-------------------|-----------------|----------------------------------|----------------------------------|
| **Python**        | 3.10.8          | Backend runtime                  | python.org                       |
| **Node.js**       | 23.9.0          | Frontend build                   | nodejs.org                       |
| **npm**           | 11.2.0          | Package manager                  | bundled with Node                |
| **Rust**          | latest stable   | Tauri desktop shell              | rustup.rs                        |
| **Docker**        | latest          | Qdrant vector database           | docker.com                       |
| **Ollama**        | latest          | Local LLM inference              | ollama.ai                        |

### 3.3 Ollama Models (Currently Installed)

| Model                           | Size    | VRAM    | Purpose                          | Status      |
|---------------------------------|---------|---------|----------------------------------|-------------|
| `qwen2.5:14b-instruct-q4_K_S`  | ~9GB    | ~8GB+   | LLM generation, reasoning        | ✅ Active   |
| `nomic-embed-text:latest`       | ~274MB  | ~274MB  | Text embeddings (768-dim)        | ✅ Active   |
| `gemma3:4b`                     | ~3GB    | ~2.5GB  | Alt generation model             | Installed   |
| `llama3.2:3b`                   | ~2GB    | ~1.8GB  | Alt generation model             | Installed   |
| `phi3:mini`                     | ~2.3GB  | ~2GB    | Fast inference fallback          | Installed   |
| `gemma3:1b`                     | ~0.8GB  | ~0.6GB  | Ultra-fast fallback              | Installed   |

> **VRAM note:** 14b model uses partial GPU offload — Ollama splits layers across your 4GB VRAM + 32GB system RAM. Expect 30–90s per LLM response. Embedding calls stay fast (<500ms, fully on GPU).

### 3.4 Minimum Requirements (Production)

| Component | Minimum                 | Recommended              |
|-----------|-------------------------|--------------------------|
| RAM       | 16GB                    | 32GB+                    |
| VRAM      | 4GB (partial offload)   | 8GB+ (full 7B GPU)       |
| Storage   | 50GB SSD                | 200GB NVMe               |
| CPU       | 6 cores                 | 8+ cores                 |
| Python    | 3.9+                    | 3.10+                    |

---

## 4. Tech Stack Deep Dive

### 4.1 Frontend

```
React 18.3  +  Vite 6.0  (inside Tauri v2 desktop shell)
│
├── Recharts 3.8 ── Radar chart, Line chart, Bar chart for results
├── Lucide React 1.8 ── All iconography (~40 icons used)
├── CSS Custom Properties ── Alpine Lab design system (no CSS framework)
│   ├── Background:  #0d1a14  (deep forest)
│   ├── Surface:     #132218 / #1a2e22
│   ├── Accent:      #3d9970  (muted jade)
│   ├── Font-mono:   JetBrains Mono (data values)
│   └── Glass panel: rgba(20,40,28,0.6) + backdrop-filter:blur(12px)
│
└── Components (9 total):
    ├── App.jsx ─────────── Root; loop state, polling, handler wiring
    ├── Sidebar.jsx ──────── Nav + live Ollama/Qdrant/DuckDB status dots
    ├── GoalPanel.jsx ────── Goal input + weight sliders + loop controls
    ├── KnowledgePanel.jsx ─ Papers/TDS cards + insight chips (mock)
    ├── ExperimentDashboard── Scored candidate cards (real + mock fallback)
    ├── DecisionPanel.jsx ── Typewriter reasoning + approval controls
    ├── ResultsPanel.jsx ─── Radar + line charts from DuckDB
    ├── PapersView.jsx ───── Upload, bulk parse, Qdrant browser, search
    ├── ExperimentsPanel.jsx─ Experiment history list
    └── ChatPanel.jsx ────── RAG chat with 3 personas
```

### 4.2 Backend

```
FastAPI 0.109  +  Uvicorn (workers=1 ← DuckDB single-writer constraint)
│
├── Routing  ── 46 REST endpoints across 8 route groups
│   ├── /api/stats           ── Live document/experiment counts
│   ├── /api/documents/*     ── CRUD + extraction data
│   ├── /api/jobs/*          ── Queue status + SSE streaming progress
│   ├── /api/bulk-*          ── Folder scanning, bulk parse SSE
│   ├── /api/search          ── Qdrant semantic search
│   ├── /api/parsed/*        ── Qdrant document browser
│   ├── /api/experiments/*   ── Experiment CRUD + predict + suggest
│   ├── /api/chat/*          ── RAG chat + session management
│   └── /api/loop/*          ── Autonomous loop orchestration (NEW)
│
├── LLM Client (llm.py)
│   ├── Custom OllamaClient (httpx, 120s timeout)
│   ├── GPU config: num_gpu=35, num_thread=8, keep_alive=-1
│   ├── JSON mode: format="json" + extract_json_from_response()
│   └── json_mode=False: returns raw Ollama response dict
│
└── langchain-ollama / langchain-qdrant (for QdrantVectorStore + OllamaEmbeddings)
    └── NOTE: dual client pattern — OllamaClient (direct) + LangChain (wrapper)
              Both active. Risk: VRAM eviction if both load model simultaneously.
```

### 4.3 Data Layer

```
┌─────────────────────────────────────────────────────┐
│                    DUCKDB 0.9.2                      │
│            (embedded, file: data/research.db)        │
│                                                      │
│  Sequences: doc_id, chunk_id, prop_id, exp_id, res_id│
│                                                      │
│  documents            chunks                         │
│  ├── id (auto)        ├── id (auto)                  │
│  ├── filename         ├── doc_id (FK)                │
│  ├── file_path        ├── content (TEXT)             │
│  ├── file_hash        ├── page_number                │
│  ├── doc_type         └── chunk_type                 │
│  ├── status                                          │
│  ├── extraction_status  material_properties          │
│  ├── extraction_conf    ├── id (auto)                │
│  ├── llm_output (JSON)  ├── doc_id (FK)              │
│  └── created_at         ├── property_name            │
│                         ├── value (TEXT)              │
│  experiments            ├── unit                     │
│  ├── id (auto)          ├── confidence               │
│  ├── name               ├── context                  │
│  ├── material_id        └── extraction_method        │
│  ├── material_name                                   │
│  ├── description      extraction_data                │
│  ├── conditions (JSON)  ├── id (PK)                  │
│  ├── expected_output    ├── doc_id (FK)              │
│  ├── actual_output      ├── data_type                │
│  ├── status             ├── content                  │
│  ├── result_analysis    └── confidence               │
│  ├── confidence_score                                │
│  ├── recommendation   experiment_results             │
│  ├── created_at         ├── id (auto)                │
│  ├── started_at         ├── experiment_id (FK)       │
│  └── completed_at       ├── metric_name             │
│                         ├── expected_value           │
│                         ├── actual_value             │
│                         ├── deviation_percent        │
│                         ├── passed (BOOLEAN)         │
│                         └── test_method             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                QDRANT (Docker container)             │
│                   localhost:6333                     │
│                                                      │
│  Collection: parsed_materials                        │
│  ├── Vectors: 768-dim (nomic-embed-text)            │
│  ├── Distance: COSINE                               │
│  ├── Points: 22 (current)                           │
│  └── Payload (LangChain nested format):             │
│      ├── page_content: (document text)              │
│      └── metadata:                                  │
│          ├── filename                               │
│          ├── doc_type   (tds / paper)               │
│          ├── doc_id     (DuckDB FK)                 │
│          ├── material_name                          │
│          ├── extraction_confidence                  │
│          ├── properties (JSON string)               │
│          ├── processing_conditions (JSON string)    │
│          ├── applications (JSON string)             │
│          ├── key_findings (JSON string)             │
│          └── processed_at (ISO timestamp)           │
│                                                     │
│  Collection: job_status                             │
│  └── 1-dim dummy vectors for job state persistence │
└─────────────────────────────────────────────────────┘
```

---

## 5. Application UI — Panel by Panel

### 5.1 Research Workspace (Main View)

```
╔══════════════════════════════════════════════════════════════════════════╗
║  MatResOps — AI Research Operator                        Loop: Iter 3 ▲ ║
╠══════════╦═══════════════════════════════════════════════════════════════╣
║          ║  ┌─────────────────────────────────────────────────────────┐ ║
║  🔬      ║  │  ⬡ GOAL CONFIGURATION                      ▲ Awaiting  │ ║
║ Research ║  │                                                          │ ║
║          ║  │  Research Goal:                    Optimization Weights: │ ║
║  📄      ║  │  ┌──────────────────────────┐  Σ = 1.00                 │ ║
║  Papers  ║  │  │ Maximize tensile strength│  Tensile   ━━━━━━━●  0.50 │ ║
║          ║  │  │ (>45 MPa) while keeping  │  Flex      ━━━━●    0.35  │ ║
║  🧪      ║  │  │ elongation >180% and     │  Cost      ━●      0.15   │ ║
║ Expmts   ║  │  │ minimizing cost...       │                            │ ║
║          ║  │  └──────────────────────────┘                            │ ║
║  📊      ║  │  [▶ Loop Active]  [❯ Run 1 Iteration]       Auto-run ⟨●⟩│ ║
║ Results  ║  └─────────────────────────────────────────────────────────┘ ║
║          ║                                                               ║
║  🧠      ║  ┌──────────────────┐  ┌──────────────────────────────────┐ ║
║ Decision ║  │ 📚 KNOWLEDGE     │  │ 🧪 EXPERIMENT DASHBOARD          │ ║
║          ║  │                  │  │                         Iter 3·3  │ ║
║  💬      ║  │ [Papers][Insights]│  │ ┌──────────────────────────────┐ │ ║
║  Chat    ║  │ 🔍 Search...     │  │ │ 🏆 Config A          Best ✓  │ │ ║
║          ║  │                  │  │ │ Score: ████████░ 0.847        │ │ ║
║ ─────    ║  │ [TDS] Makrolon   │  │ │ Tensile:53.2 Elong:210       │ │ ║
║ System   ║  │ ████ 94% match  │  │ └──────────────────────────────┘ │ ║
║ ● Ollama ║  │ [Paper] Zhang    │  │ ┌──────────────────────────────┐ │ ║
║ ● Qdrant ║  │ ████ 89% match  │  │ │ Config B            Rank #2  │ │ ║
║ ● DuckDB ║  │ ...             │  │ │ Score: ██████░░░ 0.731        │ │ ║
╚══════════╩══╩══════════════════╩══╩══════════════════════════════════════╝
```

### 5.2 Decision Panel (The Key Differentiator)

```
┌─────────────────────────────────────────────────────────────────────┐
│  🧠 Decision Reasoning                           Iteration 3        │
│                                  ● Awaiting Approval                │
├─────────────────────────────────────────────────────────────────────┤
│  [1 Retrieve] ✓ → [2 Generate] ✓ → [3 Evaluate] ✓ → [4 Decide] ● → [5 Approve]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  🏆 Selected Configuration                                          │
│  Config A                                          0.847            │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │ Tensile      │  │ Elong.       │                                │
│  │  53.2 MPa ✓  │  │  210%   ✓   │                                │
│  └──────────────┘  └──────────────┘                                │
│                                                                     │
│  SYSTEM REASONING                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Iteration 3: Config A achieved composite score 0.847,       │   │
│  │ outperforming alternatives across all weighted objectives.  │   │
│  │ The EPDM 75% + Silica 12% composition showed optimal       │   │
│  │ balance — tensile of 53.2 MPa exceeds the 45 MPa threshold │   │
│  │ while elongation of 210% surpasses the 180% floor...█      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              (typewriter animation ↑)               │
│                                                                     │
│  ▶ NEXT HYPOTHESIS                                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🔬  Iteration 4 Proposal                                    │   │
│  │     Reduce Silica to 10%, introduce cross-linker at 2%      │   │
│  │     to push tensile above 55 MPa while maintaining elong.   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  [✓ Approve & Continue]  [✏ Edit Hypothesis]          [✕ Stop Loop]│
└─────────────────────────────────────────────────────────────────────┘
```

### 5.3 Papers & TDS Library

```
┌─────────────────────────────────────────────────────────────────────┐
│ 📄 Papers & TDS Library           8 documents indexed               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐                    │
│  │  8     │  │  8     │  │  0     │  │  22    │                    │
│  │ Total  │  │  TDS   │  │ Papers │  │ Qdrant │                    │
│  └────────┘  └────────┘  └────────┘  └────────┘                    │
│                                                                     │
│  [🔍 Search parsed materials...] [Search] [Qdrant(22)] [Bulk Parse] │
├─────────────────────────────────────────────────────────────────────┤
│  Document                     Type     Status      Confidence  Date  │
│  ─────────────────────────────────────────────────────────────────  │
│  Makrolon 2607 - TDS f.pdf    ⬡ TDS   ✓ completed    87%   Apr 16  │
│  CLs1NN_Makrolon-2407.pdf     ⬡ TDS   ✓ completed    82%   Apr 16  │
│  REAFREE_C2_202892-T...pdf    ⬡ TDS   ✓ completed    79%   Apr 16  │
│  REAFREE_C2_204401-S...pdf    ⬡ TDS   ✓ completed    81%   Apr 15  │
│  ─────────────────────────────────────────────────────────────────  │
│  [+ Upload PDF]  [📁 Folder]             ← Drag & drop supported    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.4 Materials Chat

```
┌─────────────────────────────────────────────────────────────────────┐
│  💬 Materials Chat         Role: [Material Expert ▾]                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  🤖  Based on the Makrolon 2607 TDS and the REAFREE         │   │
│  │      documents in your knowledge base:                       │   │
│  │                                                              │   │
│  │      Tensile strength at 23°C (ASTM D638): 65 MPa          │   │
│  │      Elongation at break: 120%                              │   │
│  │      Flexural modulus: 2350 MPa (ISO 178)                  │   │
│  │                                                              │   │
│  │      Sources: [Makrolon 2607 TDS] [REAFREE C2 204401]      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────┐  [Send ▶]     │
│  │ Ask about materials, properties, formulations... │               │
│  └─────────────────────────────────────────────────┘               │
│  Roles: Material Expert · Technical Reviewer · Literature Researcher│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Architecture

### 6.1 Current Data State (as of April 16, 2026)

| Store     | Count          | Contents                                      |
|-----------|----------------|-----------------------------------------------|
| DuckDB    | 8 documents    | 8 TDS (Makrolon PC, REAFREE elastomers)       |
| DuckDB    | 48 properties  | Tensile, flexural, density, thermal props     |
| DuckDB    | 0 experiments  | (loop not yet run in production)              |
| Qdrant    | 22 vectors     | 768-dim embeddings of TDS content             |
| Qdrant    | 16 job vectors | Job state persistence (1-dim dummy)           |

### 6.2 Target Scale

| Metric              | Current   | Target               |
|---------------------|-----------|----------------------|
| TDS documents       | 8         | 14,000               |
| Papers              | 0         | 500+                 |
| Vector embeddings   | 22        | ~200,000             |
| Material properties | 48        | ~500,000             |
| Ingestion time      | instant   | ~12–18 hrs overnight |

---

## 7. The Autonomous Loop — State Machine

### 7.1 State Diagram

```
                    ┌─────────────────┐
                    │                 │
            ┌──────▶│      IDLE       │◀──────────┐
            │       │                 │           │
            │       └────────┬────────┘           │
            │                │                    │
            │    POST /api/loop/start              │
            │    POST /api/loop/iterate            │
            │                │                    │
            │                ▼                    │
            │       ┌─────────────────┐           │
            │  ┌───▶│                 │           │
            │  │    │    RUNNING      │           │
    stop()  │  │    │                 │           │ stop()
            │  │    └────────┬────────┘           │
            │  │             │                    │
            │  │    iteration completes           │
            │  │    (retrieve→generate→           │
            │  │     evaluate→decide→persist)     │
            │  │             │                    │
            │  │             ▼                    │
            │  │    ┌─────────────────┐           │
            │  │    │                 │           │
            │  └────│   AWAITING      │───────────┘
            │       │   APPROVAL      │
            │       │                 │
            │       └────────┬────────┘
            │                │
            │    POST /api/loop/approve
            │    (runs next iteration)
            │                │
            └────────────────┘
                  (also: stop() from any state → STOPPED)
```

### 7.2 Iteration Pipeline (what happens inside RUNNING)

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    ONE ITERATION                                 │
  │                                                                  │
  │  Step 1: RETRIEVE (active_step = 0)                             │
  │  ─────────────────────────────────                              │
  │  • Qdrant semantic search: f"{goal} {current_hypothesis}"       │
  │  • Top-5 chunks returned (cosine similarity, 768-dim)           │
  │  • Past experiment results from DuckDB (last 3)                 │
  │                                                                  │
  │  Step 2: GENERATE (active_step = 1)                             │
  │  ─────────────────────────────────                              │
  │  • LLM prompt: goal + hypothesis + context + past results       │
  │  • Output: 3 candidate formulations                             │
  │  • Schema: {label, material_name, composition, processing,      │
  │             hypothesis}                                          │
  │  • Fallback: deterministic PC/EPDM/Nylon66 configs if LLM fails │
  │                                                                  │
  │  Step 3: EVALUATE (active_step = 2)                             │
  │  ─────────────────────────────────                              │
  │  • Per candidate: predict_properties() → LLM predicts           │
  │    tensile_strength_mpa, elongation_percent, density, etc.      │
  │  • calculate_composite_score() with user weights:               │
  │    composite = Σ strength(0.5) + flex(0.35) + cost(0.15)        │
  │  • Fallback: heuristic random ±variance if LLM fails            │
  │  • Sort by composite_score descending                           │
  │                                                                  │
  │  Step 4: DECIDE (active_step = 3)                               │
  │  ─────────────────────────────────                              │
  │  • Best = scored[0]                                             │
  │  • LLM generates:                                               │
  │    - reasoning paragraph (3-5 sentences, cites properties)      │
  │    - next_hypothesis (1-2 sentences for next iteration)         │
  │  • Fallback: template-generated reasoning                       │
  │                                                                  │
  │  Step 5: PERSIST (→ AWAITING_APPROVAL)                          │
  │  ─────────────────────────────────                              │
  │  • INSERT INTO experiments (name, material_name, description,   │
  │    conditions, actual_output, result_analysis, confidence_score, │
  │    recommendation)                                               │
  │  • State → AWAITING_APPROVAL, active_step = 4                   │
  │  • Frontend shows Decision Panel with Approve/Stop/Edit buttons  │
  └─────────────────────────────────────────────────────────────────┘
```

### 7.3 Orchestrator State Object

```json
{
  "status": "awaiting_approval",
  "goal": "Maximize tensile strength (>45 MPa)...",
  "weights": { "strength": 0.50, "flexibility": 0.35, "cost": 0.15 },
  "iteration": 3,
  "active_step": 4,
  "step_names": ["Retrieve", "Generate", "Evaluate", "Decide", "Approve"],
  "candidates": [
    {
      "label": "Config A",
      "material_name": "EPDM",
      "composite_score": 0.847,
      "scores": { "strength": 0.91, "flexibility": 0.78, "cost": 0.70 },
      "predicted": { "tensile_strength": 53.2, "elongation": 210 },
      "composition": { "base_polymer": "EPDM 75%", "additives": [...] },
      "processing": { "temperature_c": 175, "cure_time_min": 20 }
    }
  ],
  "best_candidate": { ...same shape as above... },
  "reasoning": "Iteration 3: Config A achieved composite score 0.847...",
  "next_hypothesis": "Iteration 4: Reduce Silica to 10%...",
  "history": [
    { "iteration": 1, "best_label": "Config C", "best_score": 0.621, "exp_id": 1 },
    { "iteration": 2, "best_label": "Config A", "best_score": 0.741, "exp_id": 2 }
  ]
}
```

---

## 8. API Reference

### 8.1 Loop Orchestration (`/api/loop/*`)

| Method | Endpoint               | Body                              | Description                              |
|--------|------------------------|-----------------------------------|------------------------------------------|
| GET    | `/api/loop/status`     | —                                 | Current loop state (poll every 3s)       |
| POST   | `/api/loop/start`      | `{goal, weights}`                 | Reset + run iteration 1 (blocking, LLM)  |
| POST   | `/api/loop/iterate`    | —                                 | Run one more iteration (blocking, LLM)   |
| POST   | `/api/loop/approve`    | —                                 | Approve + run next iteration             |
| POST   | `/api/loop/stop`       | —                                 | Stop loop (immediate)                    |
| PUT    | `/api/loop/hypothesis` | `{hypothesis: string}`            | Edit next hypothesis before approve      |

### 8.2 Documents (`/api/documents/*`)

| Method | Endpoint                         | Description                        |
|--------|----------------------------------|------------------------------------|
| GET    | `/api/documents`                 | List all documents                 |
| POST   | `/api/documents/upload`          | Upload PDF (queues job)            |
| GET    | `/api/documents/{id}`            | Full document + chunks + properties|
| GET    | `/api/documents/{id}/properties` | Material properties only           |
| GET    | `/api/documents/{id}/extraction` | LLM extraction data                |

### 8.3 Jobs (`/api/jobs/*`)

| Method | Endpoint                   | Description                             |
|--------|----------------------------|-----------------------------------------|
| GET    | `/api/jobs`                | List all jobs (limit=50)                |
| GET    | `/api/jobs/{id}`           | Single job status                       |
| GET    | `/api/jobs/{id}/stream`    | SSE stream (real-time progress)         |
| DELETE | `/api/jobs/{id}`           | Cancel job                              |

### 8.4 Bulk Parsing (`/api/bulk-*`)

| Method | Endpoint                    | Description                         |
|--------|-----------------------------|-------------------------------------|
| POST   | `/api/bulk-parse`           | Stream-parse a folder (SSE)         |
| POST   | `/api/bulk-scan`            | Scan folder → queue all files       |
| POST   | `/api/bulk-scan-recursive`  | Recursive folder scan (SSE)         |
| POST   | `/api/bulk-scan-ui`         | Scan uploads/ folder                |

### 8.5 Experiments (`/api/experiments/*`)

| Method | Endpoint                          | Description                       |
|--------|-----------------------------------|-----------------------------------|
| GET    | `/api/experiments`                | List (filterable by status)       |
| POST   | `/api/experiments`                | Create new experiment             |
| GET    | `/api/experiments/{id}`           | Full details + results            |
| PUT    | `/api/experiments/{id}`           | Update with actual output         |
| DELETE | `/api/experiments/{id}`           | Delete                            |
| POST   | `/api/experiments/{id}/predict`   | Run LLM property prediction       |
| POST   | `/api/experiments/{id}/suggest`   | LLM next-config suggestion        |
| POST   | `/api/experiments/{id}/complete`  | Mark complete + score             |

### 8.6 Chat (`/api/chat/*`)

| Method | Endpoint                              | Description                       |
|--------|---------------------------------------|-----------------------------------|
| POST   | `/api/chat`                           | RAG chat (role + session)         |
| GET    | `/api/chat/sessions`                  | List active sessions              |
| GET    | `/api/chat/sessions/{id}/history`     | Conversation history              |
| DELETE | `/api/chat/sessions/{id}`             | Clear session                     |

### 8.7 Knowledge Search (`/api/search`, `/api/parsed/*`)

| Method | Endpoint              | Description                              |
|--------|-----------------------|------------------------------------------|
| GET    | `/api/search?q=...`   | Semantic search in Qdrant                |
| GET    | `/api/parsed`         | All Qdrant documents (flattened payload) |
| GET    | `/api/parsed/{id}`    | Single Qdrant document                   |
| DELETE | `/api/parsed/{id}`    | Delete from Qdrant                       |
| GET    | `/api/stats`          | Document + experiment counts             |

---

## 9. Codebase Map

```
E:\rlresearchassistant\
│
├── 📄 package.json              React/Tauri deps
├── 📄 vite.config.js            Vite build config
├── 📄 tsconfig.json             TypeScript config
├── 📄 index.html                Tauri entry point
│
├── 📁 src/                      React frontend (8,108 lines total)
│   ├── 📄 main.jsx              Vite entry → React.StrictMode
│   ├── 📄 App.jsx               Root component (313 lines)
│   │   ├── Loop state management (loopState, loopLoading)
│   │   ├── Polling: /api/stats (5s), /api/loop/status (3s)
│   │   └── Handler wiring: 5 loop handlers → real API calls
│   ├── 📄 index.css             Alpine Lab design system (845 lines)
│   │   ├── CSS custom properties (50+ tokens)
│   │   ├── Glass panel styles + blur effects
│   │   ├── Animations: fade-in, slide-in, pulse, spin, typewriter
│   │   └── Component styles: cards, charts, approval row
│   ├── 📄 mockData.js           Static demo data for all panels
│   │
│   └── 📁 components/
│       ├── 📄 Sidebar.jsx           (96 lines) Nav + live status dots
│       ├── 📄 GoalPanel.jsx         (144 lines) Goal + weights + loop
│       ├── 📄 KnowledgePanel.jsx    (136 lines) Papers/insights (mock)
│       ├── 📄 ExperimentDashboard.jsx(200 lines) Candidate cards
│       ├── 📄 DecisionPanel.jsx     (222 lines) Typewriter + approve
│       ├── 📄 ResultsPanel.jsx      (293 lines) Recharts radar + line
│       ├── 📄 PapersView.jsx        (630 lines) Upload + Qdrant browser
│       ├── 📄 ExperimentsPanel.jsx  (?)         Experiment history list
│       ├── 📄 ChatPanel.jsx         (?)         RAG chat UI
│       └── 📄 DocumentDetails.jsx   (?)         Document detail modal
│
├── 📁 src-tauri/                Tauri Rust shell
│   └── 📄 tauri.conf.json       App: MatResOps, 1400×900, min 1000×700
│
├── 📁 backend/                  FastAPI backend (4,280+ lines Python)
│   ├── 📄 main.py               (980 lines) 46 endpoints
│   ├── 📄 orchestrator.py       (280 lines) Loop state machine ★ NEW
│   ├── 📄 experiment_runner.py  (372 lines) Predict + score + suggest
│   ├── 📄 chat.py               (240 lines) RAG chat + 3 personas
│   ├── 📄 job_queue.py          (461 lines) Priority queue + worker
│   ├── 📄 bulk_parser.py        (449 lines) Batch parse pipeline
│   ├── 📄 extractor.py          (457 lines) TDS/paper LLM extraction
│   ├── 📄 qdrant_mgr.py         (136 lines) Vector store wrapper
│   ├── 📄 db.py                 (122 lines) DuckDB schema + init
│   ├── 📄 llm.py                (149 lines) OllamaClient HTTP wrapper
│   ├── 📄 parser.py             (208 lines) PDF text extraction
│   ├── 📄 crawler.py            (111 lines) Recursive file scan
│   ├── 📄 startup.py            (177 lines) Health check on boot
│   ├── 📄 config.py             ( 21 lines) All config constants
│   └── 📄 requirements.txt      Python dependencies
│
└── 📁 backend/data/
    ├── 📄 research.db           DuckDB database
    ├── 📁 uploads/              Uploaded PDFs staging area
    ├── 📁 parsed/               Parsed output cache
    └── 📁 qdrant_storage/       Local Qdrant persistence (if local mode)
```

---

## 10. Sprint Plan — Progress Tracker

*Original 7-day sprint. Current status: ~Day 6.5 complete.*

### ✅ Day 1 — Scaffold + Design System `[COMPLETE]`
- [x] `create-tauri-app` → Tauri v2 + React + Vite project
- [x] Alpine Lab CSS design system (50+ custom properties, glassmorphic cards)
- [x] Sidebar with 6 nav items + keyboard navigation (arrow keys, ARIA)
- [x] Empty panel layout with correct proportions
- **Deliverable:** App opens, looks stunning, navigation works

### ✅ Day 2 — Full Static UI (Mock Data) `[COMPLETE]`
- [x] GoalPanel with textarea + 3 weight sliders (Σ validation in real-time)
- [x] KnowledgePanel — paper cards + insight chips (mock data)
- [x] ExperimentDashboard — scored formulation cards with expandable detail
- [x] ResultsPanel — Recharts radar chart + line trend chart
- [x] DecisionPanel — typewriter animation reasoning + hypothesis card
- [x] All 6 views routed: Research / Papers / Experiments / Results / Decisions / Chat
- **Deliverable:** All panels populated, UX fully reviewable

### ✅ Day 3 — PDF Ingestion + DuckDB `[COMPLETE]`
- [x] Priority job queue (HIGH/MEDIUM/LOW by file size) + background worker thread
- [x] pdfplumber + PyMuPDF dual extraction (table + text)
- [x] DuckDB schema: documents, chunks, material_properties, experiments, results
- [x] SHA-256 deduplication for batch ingestion
- [x] Papers view: upload PDF → job queued → status tracked live
- [x] SSE streaming job progress endpoint
- [x] Drag & drop + folder upload in PapersView
- **Deliverable:** Can upload a TDS, see extraction status in UI

### ✅ Day 4 — Knowledge Pipeline (Embeddings + Qdrant) `[COMPLETE]`
- [x] nomic-embed-text (768-dim) via Ollama — full GPU
- [x] Qdrant collection `parsed_materials` with COSINE distance
- [x] Chunk + embed pipeline (LangChain text splitters)
- [x] Semantic search endpoint `/api/search?q=...`
- [x] Qdrant browser in PapersView (flattened payload display) ← *fixed Apr 16*
- [x] 22 vectors indexed from 8 TDS documents
- **Deliverable:** Search returns real Qdrant results

### ✅ Day 5 — Experiment Generator + Evaluation Engine `[COMPLETE]`
- [x] Goal weights → composite scoring: `Σ strength(0.5) + flex(0.35) + cost(0.15)`
- [x] `predict_properties()` — LLM predicts 6 mechanical properties from composition
- [x] `calculate_composite_score()` — heuristic weighted scoring
- [x] `suggest_next_configuration()` — LLM proposes 3 alternative configs
- [x] Experiment CRUD + results table + predict/complete endpoints
- [x] ExperimentDashboard wired to real candidates (normalization layer)
- **Deliverable:** System generates and scores 3 formulation candidates

### ✅ Day 6 — Decision Engine + Loop Wiring `[COMPLETE]`
- [x] `orchestrator.py` — full loop state machine (idle/running/awaiting/stopped)
- [x] 5-step pipeline: Retrieve → Generate → Evaluate → Decide → Persist
- [x] LLM reasoning generation (why Config X won) + next_hypothesis
- [x] Heuristic fallback at every LLM step (loop never crashes)
- [x] 6 new API endpoints: `/api/loop/{start,iterate,approve,stop,hypothesis,status}`
- [x] App.jsx handlers wired: all 5 console.log stubs → real API calls
- [x] GoalPanel: sends `{active, goal, weights}` with toggle callback
- [x] DecisionPanel: real data, inline hypothesis editor, loading states
- [x] IterBadge: live iteration count + status from `/api/loop/status`
- [x] Loop state polled every 3s; loading spinner during LLM inference
- [x] Chat working (model mismatch fixed, `.format()` crash fixed) ← *fixed Apr 16*
- **Deliverable:** Full closed loop works end-to-end ✅

### 🔲 Day 7 — Polish + Scale Test `[IN PROGRESS / REMAINING]`

#### Remaining tasks:

**Critical:**
- [ ] **Re-ingest TDS documents with 14b model** — current 22 vectors have empty `material_name` (parsed during model misconfiguration). Re-upload with correct model to populate material properties properly.
- [ ] **Tauri sidecar integration** — FastAPI currently runs standalone. Need Tauri sidecar config so Python starts with the app and stops with it.
- [ ] **Batch ingest 100+ TDS files** — run overnight to scale up knowledge base

**High priority:**
- [ ] **KnowledgePanel wire to real Qdrant** — currently shows mock papers/insights. Should call `/api/search` and `/api/parsed` with the current goal
- [ ] **Dual Ollama client consolidation** — `llm.py` OllamaClient + LangChain OllamaEmbeddings both active. Risk: VRAM eviction on 4GB GPU. Unify to single client.
- [ ] **Export decision log to PDF** — currently only JSON. pdfplumber or reportlab needed.

**Nice to have (Day 8+):**
- [ ] Multi-collection Qdrant — separate `tds_chunks` / `paper_insights` collections with relevance thresholding
- [ ] Query rephrasing CRAG-style (from `kkarthikCRAG` codebase) for better RAG retrieval
- [ ] Scientific reasoning persona (compliance/formulation expert) from `kkarthikCRAG`
- [ ] Live radar chart animations on new iteration data
- [ ] Tauri build → `.exe` installer for Windows
- [ ] Multi-user auth layer (future company deployment)

---

### Progress Summary

```
Day 1   ████████████████████  100%  Scaffold + Design System
Day 2   ████████████████████  100%  Full Static UI
Day 3   ████████████████████  100%  PDF Ingestion + DuckDB
Day 4   ████████████████████  100%  Knowledge Pipeline
Day 5   ████████████████████  100%  Experiment Generator + Scoring
Day 6   ████████████████████  100%  Decision Engine + Loop Wiring
Day 7   █████████░░░░░░░░░░░   45%  Polish + Scale Test
─────────────────────────────────────────────
Overall ████████████████░░░░   92%  of 7-day sprint
```

---

## 11. Running the System

### Prerequisites

```bash
# 1. Start Qdrant (Docker)
docker run -d -p 6333:6333 -p 6334:6334 \
  -v "E:/rlresearchassistant/backend/data/qdrant_storage:/qdrant/storage:z" \
  qdrant/qdrant

# 2. Start Ollama (Windows — should already be in system tray)
#    Verify models are available:
ollama list
# Should show: qwen2.5:14b-instruct-q4_K_S  nomic-embed-text  gemma3:4b  etc.

# 3. If 14b model not pulled yet:
ollama pull qwen2.5:14b-instruct-q4_K_S
ollama pull nomic-embed-text
```

### Start the Backend

```bash
cd E:\rlresearchassistant\backend

# Install dependencies (first time only)
pip install -r requirements.txt

# Start FastAPI (MUST be workers=1 for DuckDB)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --reload

# Health check
curl http://localhost:8000/health
# Expected: {"status":"healthy","ollama":"running","qdrant":"connected"}
```

### Start the Frontend

```bash
cd E:\rlresearchassistant

# Install Node dependencies (first time only)
npm install

# Development mode (Vite hot-reload, no Tauri shell)
npm run dev
# → Open http://localhost:5173

# Development mode WITH Tauri desktop window
npm run tauri dev
# → Opens native window at 1400×900
```

### First-Time Data Setup

```bash
# Upload your TDS PDFs via the Papers view
# OR use the bulk parse API directly:
curl -X POST http://localhost:8000/api/bulk-parse \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "E:\\path\\to\\your\\tds\\folder", "resume": true}'

# Monitor progress via SSE stream (or watch the Papers view in the UI)
```

### Run the Research Loop

1. Open the app → navigate to **Research** view
2. In **Goal Configuration**: type your research goal, set property weights
3. Click **▶ Start Research Loop** (or **❯ Run 1 Iteration** for a single step)
4. Wait for LLM inference (~30–90s for 14b model)
5. Review the **Decision Reasoning** panel — winner, scoring, reasoning
6. Click **✓ Approve & Continue** to run next iteration, or **✏ Edit Hypothesis** to adjust
7. Repeat until satisfied, then **✕ Stop Loop**

---

## 12. Known Issues & Limitations

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| DuckDB single-writer | ⚠️ Medium | Known | `uvicorn --workers 1` required |
| Dual Ollama clients | ⚠️ Medium | Known | VRAM eviction risk on 4GB GPU |
| No Tauri sidecar | 🔲 Low | Planned | FastAPI runs standalone |
| Empty `material_name` in Qdrant | ℹ️ Info | Data issue | Re-ingest with correct model |
| KnowledgePanel still mock | 🔲 Low | Planned | Day 7 task |
| LLM response time 30–90s | ℹ️ Info | By design | 14b model on partial offload |
| No authentication | 🔲 Low | Future | Single user for now |

---

## 13. Roadmap — What's Left

### Phase 7 (Current — Polish & Scale)
- Tauri sidecar bundling (Python packaged with .exe)
- Re-ingest TDS corpus with 14b model
- KnowledgePanel wired to real Qdrant search
- Export decision log to PDF
- UI loading states + error boundaries

### Phase 8 (Post-Sprint — CRAG Merge from `kkarthikCRAG`)
- **Relevance thresholding** — skip low-score chunks from RAG context
- **Query rephrasing** — if retrieval score < 0.7, rephrase query and retry
- **Multi-collection Qdrant** — `tds_chunks` / `paper_insights` separate namespaces
- **Scientific reasoning** compliance persona (REACH, RoHS, ASTM references)

### Phase 9 (Company Deployment)
- Multi-user auth (JWT or OAuth2)
- PostgreSQL migration from DuckDB
- Shared Qdrant cluster (remote)
- Role-based access: Researcher / Reviewer / Admin
- Audit trail for all decisions
- Tauri auto-updater

---

## Contributing & Development Notes

- **Single DuckDB writer**: never run with `--workers > 1`
- **LLM calls are blocking** — orchestrator runs them in `asyncio.run_in_executor` to avoid starving the FastAPI event loop
- **JSON mode safety**: always use `.replace("{context}", ...)` not `.format()` when building prompts — document text can contain `{}` (JSON, citations)
- **Qdrant payload format**: LangChain stores metadata nested under a `"metadata"` key. The `get_all_documents()` flattener handles this transparently.
- **Model keep_alive=-1**: models stay loaded in VRAM indefinitely — good for batch ingestion, bad if you need to switch models mid-session

---

*Built for Planet Material Labs · April 2026 · MatResOps v0.1.0*  
*Stack: Tauri v2 · React 18 · FastAPI 0.109 · Ollama · Qdrant · DuckDB · Python 3.10*
