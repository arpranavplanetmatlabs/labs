import subprocess
import time
import requests

proc = subprocess.Popen(
    ["python", "main.py"],
    cwd="E:/rlresearchassistant/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

print("Waiting for server...")
time.sleep(8)

try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print("Health:", r.json())

    r = requests.get("http://localhost:8000/api/stats", timeout=5)
    print("Stats:", r.json())
except Exception as e:
    print("Error:", e)
    print("Reading logs:")
    for line in proc.stdout:
        print(line)
finally:
    proc.terminate()
    proc.wait()
