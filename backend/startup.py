import subprocess
import time
import sys
import os
import httpx
from pathlib import Path

EMBED_MODEL = "nomic-embed-text"
EXTRACTION_MODEL = "qwen2.5:7b-instruct-q4_K_S"


def print_status(msg: str, color: str = ""):
    if color == "green":
        print(f"[OK] {msg}")
    elif color == "yellow":
        print(f"[WAIT] {msg}")
    elif color == "red":
        print(f"[ERROR] {msg}")
    else:
        print(f"[INFO] {msg}")


def is_ollama_running() -> bool:
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        return response.status_code == 200
    except:
        return False


def start_ollama():
    print_status("Starting Ollama service...", "yellow")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        for i in range(30):
            time.sleep(2)
            if is_ollama_running():
                print_status("Ollama service started", "green")
                return True

        print_status("Failed to start Ollama within 60 seconds", "red")
        return False
    except FileNotFoundError:
        print_status(
            "Ollama not found. Please install Ollama from https://ollama.com", "red"
        )
        return False
    except Exception as e:
        print_status(f"Failed to start Ollama: {e}", "red")
        return False


def get_installed_models() -> list:
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    except:
        pass
    return []


def pull_model(model: str) -> bool:
    print_status(f"Pulling model: {model}...", "yellow")
    print_status("(This may take a few minutes on first run)", "")
    try:
        process = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        while True:
            result = process.poll()
            if result is not None:
                if result == 0:
                    print_status(f"Model {model} installed", "green")
                    return True
                else:
                    print_status(f"Failed to pull {model}", "red")
                    return False
            time.sleep(5)

    except Exception as e:
        print_status(f"Failed to pull {model}: {e}", "red")
        return False


def check_and_start_ollama() -> bool:
    print_status("Checking Ollama status...")

    if is_ollama_running():
        print_status("Ollama is already running", "green")
        return True

    print_status("Ollama is not running")

    response = input("Start Ollama now? (y/n): ").strip().lower()
    if response != "y":
        print_status("Ollama startup skipped. Backend may not work properly.", "yellow")
        return False

    return start_ollama()


def ensure_models():
    installed = get_installed_models()

    models_to_check = [EMBED_MODEL, EXTRACTION_MODEL]

    for model in models_to_check:
        if model in installed:
            print_status(f"Model {model} is installed", "green")
        else:
            print_status(f"Model {model} is not installed", "yellow")
            response = input(f"Pull {model}? (y/n): ").strip().lower()
            if response == "y":
                if not pull_model(model):
                    print_status(
                        f"Warning: {model} installation failed. Some features may not work.",
                        "yellow",
                    )
            else:
                print_status(
                    f"Warning: {model} not installed. Some features may not work.",
                    "yellow",
                )


def start_backend():
    print_status("Starting FastAPI backend...")
    try:
        import uvicorn
        from main import app

        print_status("=" * 50)
        print_status("All services ready!", "green")
        print_status("Backend running at http://localhost:8000", "green")
        print_status("API docs at http://localhost:8000/docs", "green")
        print_status("=" * 50)

        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        print_status(f"Failed to start backend: {e}", "red")
        return False


def main():
    print("=" * 50)
    print("  Planet Material Labs Backend Startup")
    print("=" * 50)
    print()

    if not check_and_start_ollama():
        print()
        print_status(
            "Ollama not running. Backend will start but LLM features may not work.",
            "yellow",
        )

    print()
    ensure_models()

    print()
    start_backend()


if __name__ == "__main__":
    main()
