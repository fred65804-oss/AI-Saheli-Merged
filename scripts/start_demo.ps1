# start_demo.ps1 — one-command, demo-day startup for AI Saheli.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
#
# What it does (in order, so the first live question is never slow):
#   1. Starts the FastAPI backend (uvicorn, port 8000) in its own window.
#   2. Waits until /health answers.
#   3. Fires POST /warmup — preloads KB embedder, both LLM clients,
#      faster-whisper ASR and edge-tts TTS. THIS IS THE SLOW PART (~20-60s
#      warm cache, several minutes on a brand-new machine downloading models).
#   4. Starts the Next.js frontend (port 3000) in this window.
#
# Stop: Ctrl+C here kills the frontend; close the backend window separately.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot   # repo root (scripts/..)

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: .venv not found at $Python — create it and pip install -r requirements.txt first." -ForegroundColor Red
    exit 1
}

# --- 1. Backend -------------------------------------------------------------
$healthUrl = "http://127.0.0.1:8000/health"
$alreadyUp = $false
try {
    Invoke-RestMethod $healthUrl -TimeoutSec 2 | Out-Null
    $alreadyUp = $true
    Write-Host "Backend already running on :8000 — reusing it." -ForegroundColor Yellow
} catch {}

if (-not $alreadyUp) {
    Write-Host "Starting backend (uvicorn :8000) in a new window..." -ForegroundColor Cyan
    Start-Process -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "apps.backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $Root
}

# --- 2. Wait for /health ----------------------------------------------------
Write-Host "Waiting for backend health..." -NoNewline
$deadline = (Get-Date).AddSeconds(90)
while ($true) {
    try {
        $h = Invoke-RestMethod $healthUrl -TimeoutSec 3
        Write-Host " OK (llm=$($h.llm), provider=$($h.provider))" -ForegroundColor Green
        break
    } catch {
        if ((Get-Date) -gt $deadline) {
            Write-Host "`nERROR: backend did not come up within 90s. Check the uvicorn window." -ForegroundColor Red
            exit 1
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

# --- 3. Warmup (KB + LLM + ASR + TTS) ----------------------------------------
Write-Host "Warming up KB / LLM / voice models (can take a few minutes on first-ever run)..." -ForegroundColor Cyan
try {
    $w = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/warmup" -TimeoutSec 600
    Write-Host ("Warmup done in {0}s : kb={1} llm_fast={2} llm_main={3} asr={4} tts={5}" -f `
        [math]::Round($w.took_ms / 1000, 1), $w.kb_chunks_returned, $w.llm_fast, $w.llm_main, $w.asr, $w.tts) -ForegroundColor Green
} catch {
    Write-Host "WARNING: warmup call failed ($_). The first live question will be slow." -ForegroundColor Yellow
}

# --- 4. Frontend --------------------------------------------------------------
Write-Host "Starting frontend (Next.js :3000)... open http://localhost:3000" -ForegroundColor Cyan
Set-Location (Join-Path $Root "apps\web")
npm run dev
