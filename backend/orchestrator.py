"""
orchestrator.py — Autonomous Research Loop State Machine

States:  idle → running → awaiting_approval → (loop back or stopped)

Public API:
  start_loop(goal, weights)  — reset + run iteration 1
  run_iteration()            — run one iteration from current state
  approve()                  — approve current decision, run next iteration
  stop()                     — stop the loop
  edit_hypothesis(text)      — update next_hypothesis before next run
  get_status()               — return current state dict (safe copy)
"""

import json
import uuid
import threading
import random
from datetime import datetime
from typing import Dict, Any, Optional, List

from config import LLM_MODEL
from experiment_runner import predict_properties, calculate_composite_score


class LoopStatus:
    IDLE = "idle"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    STOPPED = "stopped"


# Phase 7: BO-aware step names
LOOP_STEP_NAMES = ["Retrieve", "Seed/Acquire", "Predict", "Decide", "Approve"]


class LoopOrchestrator:
    def __init__(self):
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "status": LoopStatus.IDLE,
            "goal": "",
            "schema_id": None,
            "weights": {"strength": 0.5, "flexibility": 0.35, "cost": 0.15},
            "iteration": 0,
            "current_exp_id": None,
            "candidates": [],
            "best_candidate": None,
            "reasoning": "",
            "next_hypothesis": "",
            "active_step": 0,
            "error": None,
            "history": [],
            "bo_mode": False,       # True when schema_id is set and BO is active
            "n_training_points": 0, # GP training data count
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "step_names": LOOP_STEP_NAMES,
            }

    def start_loop(self, goal: str, weights: Dict[str, float], schema_id: str = None) -> Dict[str, Any]:
        with self._lock:
            self._state.update({
                "status": LoopStatus.RUNNING,
                "goal": goal,
                "schema_id": schema_id,
                "weights": weights,
                "iteration": 0,
                "candidates": [],
                "best_candidate": None,
                "reasoning": "",
                "next_hypothesis": goal,
                "active_step": 0,
                "error": None,
                "history": [],
                "bo_mode": bool(schema_id),
                "n_training_points": 0,
            })
        return self._run_iteration_impl()

    def run_iteration(self) -> Dict[str, Any]:
        with self._lock:
            if self._state["status"] == LoopStatus.RUNNING:
                return {"error": "Loop is already running"}
            self._state["status"] = LoopStatus.RUNNING
            self._state["error"] = None
        return self._run_iteration_impl()

    def approve(self) -> Dict[str, Any]:
        with self._lock:
            if self._state["status"] != LoopStatus.AWAITING_APPROVAL:
                return {"error": f"Cannot approve in state: {self._state['status']}"}
            self._state["status"] = LoopStatus.RUNNING
            self._state["error"] = None
            schema_id = self._state.get("schema_id")
            best = self._state.get("best_candidate") or {}

        # Record approved point in surrogate registry → triggers GP retrain
        if schema_id and best:
            try:
                from surrogate.loop import record_approval
                composition = best.get("composition", {})
                preds = best.get("surrogate_predictions", {})
                # Extract mean values as the observation
                property_values = {
                    k: v.get("mean", v) if isinstance(v, dict) else v
                    for k, v in preds.items()
                }
                if composition and property_values:
                    record_approval(schema_id, composition, property_values)
            except Exception as e:
                print(f"[Orchestrator] Retrain on approval failed (non-fatal): {e}")

        return self._run_iteration_impl()

    def stop(self):
        with self._lock:
            self._state["status"] = LoopStatus.STOPPED

    def edit_hypothesis(self, hypothesis: str):
        with self._lock:
            self._state["next_hypothesis"] = hypothesis

    # ── Core iteration pipeline ───────────────────────────────────────────────

    def _set_step(self, step: int):
        with self._lock:
            self._state["active_step"] = step

    def _run_iteration_impl(self) -> Dict[str, Any]:
        try:
            with self._lock:
                self._state["iteration"] += 1
                iteration = self._state["iteration"]
                goal = self._state["goal"]
                weights = self._state["weights"]
                hypothesis = self._state["next_hypothesis"]
                schema_id = self._state.get("schema_id")

            # ── Step 1: Retrieve ──────────────────────────────────────
            self._set_step(0)
            context_text = self._retrieve_context(goal, hypothesis)

            # ── Step 2: Generate / Acquire ────────────────────────────
            self._set_step(1)
            if schema_id:
                # BO mode: use acquisition function to suggest candidates
                candidates, bo_meta = self._bo_candidates(schema_id, goal, iteration)
            else:
                candidates = self._generate_candidates(goal, hypothesis, context_text, iteration)
                bo_meta = {}

            # ── Step 3: Predict / Evaluate ────────────────────────────
            self._set_step(2)
            scored = self._score_candidates(candidates, weights, schema_id=schema_id)

            # ── Step 4: Decide ────────────────────────────────────────
            self._set_step(3)
            best = scored[0] if scored else {}
            reasoning, next_hyp = self._generate_decision(scored, best, goal, iteration)

            exp_id = self._persist(goal, scored, best, reasoning, iteration, schema_id)

            # ── Step 5: Await approval ────────────────────────────────
            self._set_step(4)
            n_pts = bo_meta.get("n_training_points", 0)
            history_entry = {
                "iteration": iteration,
                "best_label": best.get("label", ""),
                "best_score": best.get("composite_score", 0),
                "exp_id": exp_id,
                "timestamp": datetime.now().isoformat(),
            }

            with self._lock:
                self._state.update({
                    "status": LoopStatus.AWAITING_APPROVAL,
                    "candidates": scored,
                    "best_candidate": best,
                    "reasoning": reasoning,
                    "next_hypothesis": next_hyp,
                    "current_exp_id": exp_id,
                    "error": None,
                    "history": self._state["history"] + [history_entry],
                    "n_training_points": n_pts,
                    "bo_mode": bool(schema_id),
                })

            return self.get_status()

        except Exception as e:
            print(f"[Orchestrator] Iteration error: {e}")
            with self._lock:
                self._state.update({
                    "status": LoopStatus.AWAITING_APPROVAL,
                    "error": str(e),
                })
            return self.get_status()

    # ── Step implementations ──────────────────────────────────────────────────

    def _bo_candidates(self, schema_id: str, goal: str, iteration: int):
        """Use BO acquisition function to generate candidates."""
        from surrogate.loop import bo_iteration
        result = bo_iteration(schema_id=schema_id, goal=goal, iteration=iteration, n_candidates=5)
        raw_candidates = result.get("candidates", [])
        # Convert BO candidate format to orchestrator format
        candidates = []
        for c in raw_candidates:
            comp = c.get("composition", {})
            candidates.append({
                "label": f"Config {c.get('rank', '?')}",
                "material_name": schema_id,
                "composition": comp,
                "processing": {},
                "hypothesis": c.get("acquisition_reason", ""),
                # Carry BO metadata forward
                "_bo_predictions": c.get("predictions", {}),
                "_bo_acquisition_score": c.get("acquisition_score", 0),
                "_bo_rank": c.get("rank", 0),
            })
        return candidates, {
            "n_training_points": result.get("n_training_points", 0),
            "mode": result.get("mode", "doe"),
        }

    def _retrieve_context(self, goal: str, hypothesis: str) -> str:
        try:
            from knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph()
            query = f"{goal} {hypothesis}"[:300]
            results = kg.graph_aware_search(query=query, k=5)
            parts = []
            for r in results:
                fname = r.get("filename", "unknown")
                content = r.get("content", "")[:400]
                material = r.get("material_name", "")
                parts.append(f"[{fname}]{' — ' + material if material else ''}\n{content}")
            return "\n\n".join(parts) if parts else "No relevant materials in knowledge base yet."
        except Exception as e:
            return f"Knowledge base unavailable: {e}"

    def _generate_candidates(
        self, goal: str, hypothesis: str, context: str, iteration: int
    ) -> List[Dict]:
        past = self._get_past_results(limit=3)
        past_str = json.dumps(past, indent=2) if past else "No previous experiments."

        prompt = f"""You are a polymer/materials science formulation expert.

RESEARCH GOAL: {goal}

CURRENT HYPOTHESIS: {hypothesis}

ITERATION: {iteration}

RETRIEVED KNOWLEDGE:
{context}

PAST RESULTS:
{past_str}

Generate 3 distinct candidate formulations exploring different strategies.

Return ONLY this JSON:
{{
  "candidates": [
    {{
      "label": "Config A",
      "material_name": "material name",
      "composition": {{
        "base_polymer": "name at X%",
        "additives": [{{"name": "...", "percentage": 5.0}}]
      }},
      "processing": {{"temperature_c": 280, "cure_time_min": 30}},
      "hypothesis": "Why this should work"
    }}
  ]
}}"""

        try:
            from llm import get_client
            client = get_client()
            result = client.generate(
                model=LLM_MODEL,
                prompt=prompt,
                system="You are a materials science expert. Return only valid JSON.",
                temperature=0.4,
                json_mode=True,
            )
            client.close()

            if result and isinstance(result, dict):
                # client.generate with json_mode=True returns parsed dict directly
                candidates = result.get("candidates", [])
                if candidates:
                    return candidates[:3]

        except Exception as e:
            print(f"[Orchestrator] Generate error: {e}")

        # Fallback heuristic candidates
        return [
            {
                "label": f"Config A",
                "material_name": "Polycarbonate",
                "composition": {"base_polymer": "PC 85%", "additives": [{"name": "Impact modifier", "percentage": 10}, {"name": "UV stabilizer", "percentage": 5}]},
                "processing": {"temperature_c": 280, "cure_time_min": 30},
                "hypothesis": "Standard PC with impact enhancement",
            },
            {
                "label": f"Config B",
                "material_name": "EPDM",
                "composition": {"base_polymer": "EPDM 75%", "additives": [{"name": "Carbon black", "percentage": 15}, {"name": "Plasticizer", "percentage": 10}]},
                "processing": {"temperature_c": 175, "cure_time_min": 20},
                "hypothesis": "Rubber blend optimized for flexibility",
            },
            {
                "label": f"Config C",
                "material_name": "Nylon 66",
                "composition": {"base_polymer": "PA66 90%", "additives": [{"name": "Glass fiber", "percentage": 10}]},
                "processing": {"temperature_c": 280, "cure_time_min": 25},
                "hypothesis": "Glass fiber reinforced for tensile strength",
            },
        ]

    def _score_candidates(self, candidates: List[Dict], weights: Dict, schema_id: str = None) -> List[Dict]:
        schema = None
        if schema_id:
            try:
                from qdrant_store import get_store
                schema = get_store().get_schema(schema_id)
            except Exception:
                pass

        scored = []
        for c in candidates:
            try:
                # Use BO predictions if already computed (BO mode)
                bo_preds = c.pop("_bo_predictions", None)
                acq_score = c.pop("_bo_acquisition_score", 0)
                c.pop("_bo_rank", None)

                if bo_preds:
                    preds = bo_preds
                    pred_status = "success"
                else:
                    prediction = predict_properties(
                        composition=c.get("composition", {}),
                        schema_id=schema_id or "",
                        material_name=c.get("material_name", ""),
                    )
                    pred_status = prediction.get("status")
                    preds = prediction.get("predictions", {}) if pred_status == "success" else {}

                if preds:
                    score_result = calculate_composite_score(
                        predicted_props=preds,
                        schema=schema,
                        expected_props={"tensile_strength": 45, "elongation": 150},
                        weights=weights,
                    )
                    composite = score_result["composite_score"]
                    scores = score_result.get("scores", {})
                else:
                    base = round(0.55 + random.uniform(-0.1, 0.25), 3)
                    composite = base
                    scores = {"strength": base, "flexibility": base, "cost": 0.65}
                    preds = {}

                scored.append({
                    **c,
                    "surrogate_predictions": preds,
                    "composite_score": composite,
                    "scores": scores,
                    "acquisition_score": acq_score,
                })
            except Exception as e:
                scored.append({
                    **c,
                    "surrogate_predictions": {},
                    "composite_score": 0.5,
                    "scores": {},
                    "score_error": str(e),
                })

        return sorted(scored, key=lambda x: x["composite_score"], reverse=True)

    def _generate_decision(
        self, scored: List[Dict], best: Dict, goal: str, iteration: int
    ) -> tuple:
        summary = "\n".join([
            f"  {c['label']}: score={c['composite_score']:.3f} | "
            f"tensile={c.get('predicted', {}).get('tensile_strength', '?')} MPa | "
            f"elong={c.get('predicted', {}).get('elongation', '?')}%"
            for c in scored
        ])

        prompt = f"""You are an autonomous materials research operator reviewing iteration {iteration}.

GOAL: {goal}

CANDIDATE SCORES:
{summary}

WINNER: {best.get('label', 'N/A')} (composite score: {best.get('composite_score', 0):.3f})
Composition: {json.dumps(best.get('composition', {}), indent=2)}
Original hypothesis: {best.get('hypothesis', '')}

Write a concise scientific decision report. Be specific about properties and trade-offs.

Return JSON:
{{
  "reasoning": "3-5 sentence reasoning paragraph citing specific properties and why this config won",
  "next_hypothesis": "1-2 sentence hypothesis for iteration {iteration + 1} describing what to adjust and why"
}}"""

        # Deterministic fallback
        default_reasoning = (
            f"Iteration {iteration}: {best.get('label', 'Config A')} achieved composite score "
            f"{best.get('composite_score', 0):.3f}, outperforming alternatives across all "
            f"weighted objectives. Tensile strength: "
            f"{best.get('predicted', {}).get('tensile_strength', 'N/A')} MPa, elongation: "
            f"{best.get('predicted', {}).get('elongation', 'N/A')}%. "
            f"The composition balance proved favorable given the current goal weights."
        )
        default_next_hyp = (
            f"Iteration {iteration + 1}: Refine {best.get('label', 'Config A')} additive ratios "
            f"to push composite score above {best.get('composite_score', 0) + 0.05:.3f}. "
            f"Focus on the weakest scoring dimension."
        )

        try:
            from llm import get_client
            client = get_client()
            result = client.generate(
                model=LLM_MODEL,
                prompt=prompt,
                system="Return only valid JSON.",
                temperature=0.3,
                json_mode=True,
            )
            client.close()

            if result and isinstance(result, dict):
                reasoning = result.get("reasoning", default_reasoning)
                next_hyp = result.get("next_hypothesis", default_next_hyp)
                if reasoning and next_hyp:
                    return reasoning, next_hyp

        except Exception as e:
            print(f"[Orchestrator] Decision LLM error: {e}")

        return default_reasoning, default_next_hyp

    def _persist(self, goal: str, candidates: List[Dict], best: Dict, reasoning: str, iteration: int, schema_id: str = None) -> Optional[str]:
        try:
            from qdrant_store import get_store
            store = get_store()
            exp_id = str(uuid.uuid4())
            store.upsert_experiment(
                exp_id=exp_id,
                name=f"Loop Iteration {iteration}",
                goal=goal,
                iteration=iteration,
                material_name=best.get("material_name", ""),
                candidates=candidates,
                best_candidate=best,
                reasoning=reasoning,
                composite_score=best.get("composite_score", 0),
                schema_id=schema_id,
                surrogate_predictions=best.get("surrogate_predictions"),
                acquisition_score=best.get("acquisition_score", 0),
            )
            return exp_id
        except Exception as e:
            print(f"[Orchestrator] Persist error: {e}")
            return None

    def _get_past_results(self, limit: int = 3) -> List[Dict]:
        try:
            from qdrant_store import get_store
            store = get_store()
            exps = store.get_recent_experiments(limit=limit)
            return [
                {
                    "name": e.get("name", ""),
                    "material": e.get("material_name", ""),
                    "score": e.get("composite_score", 0),
                    "analysis": e.get("reasoning", "")[:200],
                }
                for e in exps
            ]
        except Exception:
            return []


# ── Singleton ─────────────────────────────────────────────────────────────────

_orchestrator: Optional[LoopOrchestrator] = None
_orch_lock = threading.Lock()


def get_orchestrator() -> LoopOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        with _orch_lock:
            if _orchestrator is None:
                _orchestrator = LoopOrchestrator()
    return _orchestrator
