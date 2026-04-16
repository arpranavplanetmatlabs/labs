@echo off
echo ========================================
echo   Planet Material Labs Backend Startup
echo ========================================
echo.

cd /d "%~dp0"

echo [INFO] Checking Ollama status...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Ollama is running
) else (
    echo [WAIT] Ollama not running, starting...
    start /min cmd /c "ollama serve"
    echo [INFO] Waiting for Ollama to start (30 seconds)...
    timeout /t 30 /nobreak >nul
    
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Ollama started successfully
    ) else (
        echo [WARNING] Ollama may not have started properly
        echo [INFO] Check if Ollama is installed: https://ollama.com
    )
)

echo.
echo [INFO] Checking required models...

curl -s http://localhost:11434/api/tags | findstr /C:"nomic-embed-text" >nul
if %errorlevel% equ 0 (
    echo [OK] nomic-embed-text installed
) else (
    echo [WAIT] nomic-embed-text not found
    echo [INFO] Run: ollama pull nomic-embed-text
)

curl -s http://localhost:11434/api/tags | findstr /C:"phi3.5" >nul
if %errorlevel% equ 0 (
    echo [OK] phi3.5 installed
) else (
    echo [WAIT] phi3.5:3b not found
    echo [INFO] Run: ollama pull phi3.5:3b
)

echo.
echo ========================================
echo   Starting Backend Server
echo ========================================
echo.

python main.py

pause
