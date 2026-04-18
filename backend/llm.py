import httpx
import json
import re
from typing import Optional, Dict, Any, List
from config import OLLAMA_BASE, EMBED_MODEL, LLM_MODEL

AVAILABLE_MODELS = [
    "phi3:mini",
    "qwen2.5:3b-instruct-q4_K_S",
    "qwen2.5:7b-instruct-q4_K_S",
    "qwen2.5:14b-instruct-q4_K_S",
    "llama3.2:3b",
    "gemma3:4b",
]


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE):
        self.base_url = base_url
        self.client = httpx.Client(timeout=300.0)

    def is_running(self) -> bool:
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> List[str]:
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
            return []
        except:
            return []

    def pull_model(self, model: str) -> bool:
        try:
            response = self.client.post(
                f"{self.base_url}/api/pull", json={"name": model}, timeout=None
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to pull model {model}: {e}")
            return False

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = True,
    ) -> Optional[Dict[str, Any]]:
        # GPU Optimization: num_gpu offloads layers to RTX 3050
        # keep_alive: -1 keeps model in VRAM for the full 14,000 file run
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_gpu": 99,   # offload all layers to GPU (3b fits in 4GB VRAM)
                "num_ctx": 8192, # 4000-char chunk (~1000 tok) + system prompt (~450 tok) + JSON response — well within limit
            },
            "keep_alive": "15m",
        }

        if system:
            payload["system"] = system

        if json_mode:
            payload["format"] = "json"

        try:
            response = self.client.post(f"{self.base_url}/api/generate", json=payload)
            if response.status_code == 200:
                result = response.json()
                if json_mode and "response" in result:
                    raw_response = result["response"]
                    parsed = extract_json_from_response(raw_response)
                    return parsed if parsed is not None else {"raw_text": raw_response}
                return result
            return None
        except Exception as e:
            print(f"Generation error: {e}")
            return None

    def embeddings(self, text: str, model: str = EMBED_MODEL) -> Optional[List[float]]:
        try:
            payload = {"model": model, "prompt": text, "options": {"num_gpu": 35}}
            response = self.client.post(f"{self.base_url}/api/embeddings", json=payload)
            if response.status_code == 200:
                data = response.json()
                return data.get("embedding")
            return None
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    def close(self):
        self.client.close()


def get_client() -> OllamaClient:
    return OllamaClient()


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    text = text.strip()

    # Handle Markdown code blocks
    if "```json" in text:
        try:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        except:
            pass
    elif "```" in text:
        try:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        except:
            pass

    # Direct JSON attempt
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except:
            pass

    # Regex search for the first valid-looking JSON object
    try:
        # Matches balanced curly braces
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    except:
        pass

    return None
