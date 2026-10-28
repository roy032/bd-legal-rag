# One-command setup for Windows: SETUP_WINDOWS.bat runs this.
#
#   1. Python 3.10+   (installed with winget if missing)
#   2. .venv with the package, the web service and the embedding model library
#   3. Ollama         (installed with winget if missing) and the answering model
#   4. The law index  (kept if present; else downloaded from a Hugging Face dataset,
#                      or built here: a starter set of Acts or the full corpus)
#   5. bdrag start    (127.0.0.1 only, local model, opens the browser)
#
# Safe to run again: every step is skipped when it is already done.
# Options:  -Index starter|full|download|skip   -IndexRepo <you>/bdrag-index
#           -Model gemma4:e4b   -Port 8000   -NoStart
# Kept to ASCII: Windows PowerShell 5.1 reads a script without a BOM as ANSI.
param(
  [ValidateSet("ask", "starter", "full", "download", "skip")] [string]$Index = "ask",
  [string]$IndexRepo = $env:BDRAG_INDEX_REPO,
  [string]$Model = "gemma4:e4b",
  [int]$Port = 8000,
  [switch]$NoStart
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = "1"
$Py = ".venv\Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "!! $text" -ForegroundColor Red; exit 1 }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}
function Run($exe, [string[]]$argv) {
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { Fail "'$exe $($argv -join ' ')' failed (exit $LASTEXITCODE). Scroll up for the reason." }
}
function Winget-Install($id, $what) {
  if (-not (Have "winget")) {
    Fail "$what is not installed and winget is not available. Install $what yourself, then run this again."
  }
  Write-Host "Installing $what with winget..."
  winget install -e --id $id --accept-source-agreements --accept-package-agreements --scope user
  if ($LASTEXITCODE -ne 0) {
    winget install -e --id $id --accept-source-agreements --accept-package-agreements
  }
  Refresh-Path
}

# A Python that is really 3.10+ (the Microsoft Store "python" stub is not).
function Find-Python {
  $candidates = @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("py", "-3"), @("python"))
  foreach ($c in $candidates) {
    if (-not (Have $c[0])) { continue }
    $argv = @($c | Select-Object -Skip 1) + @("-c", "import sys; print(sys.version_info >= (3, 10))")
    try { $ok = & $c[0] @argv 2>$null } catch { continue }
    if ($ok -eq "True") { return ,$c }
  }
  return $null
}

Write-Host "Bangladesh Law Assistant: free, Bangla first, and private on this computer." -ForegroundColor Green

# 1 ---------------------------------------------------------------- Python
Step "1/5 Python"
if (Test-Path $Py) {
  Write-Host "Using the existing .venv"
} else {
  $python = Find-Python
  if (-not $python) {
    Winget-Install "Python.Python.3.12" "Python 3.12"
    $python = Find-Python
    if (-not $python) { Fail "Python was installed but is not on PATH yet. Close this window and run SETUP_WINDOWS.bat again." }
  }
  Write-Host "Creating .venv with $($python -join ' ')"
  $argv = @($python | Select-Object -Skip 1) + @("-m", "venv", ".venv")
  Run $python[0] $argv
}

# 2 ---------------------------------------------------------------- packages
Step "2/5 Packages (the first time downloads about 1 GB)"
Run $Py @("-m", "pip", "install", "-q", "--upgrade", "pip")
Run $Py @("-m", "pip", "install", "-q", "-e", ".[serve,embed]")

# 3 ---------------------------------------------------------------- Ollama + model
Step "3/5 Ollama and the answering model ($Model)"
$ollama = (Get-Command "ollama" -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
  $guess = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
  if (Test-Path $guess) { $ollama = $guess }
}
if (-not $ollama) {
  Winget-Install "Ollama.Ollama" "Ollama"
  $ollama = (Get-Command "ollama" -ErrorAction SilentlyContinue).Source
  if (-not $ollama) { $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
  if (-not (Test-Path $ollama)) { Fail "Ollama was installed but not found. Close this window and run SETUP_WINDOWS.bat again." }
}
$env:OLLAMA_HOST = "127.0.0.1:11434"
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null }
catch {
  Write-Host "Starting Ollama..."
  Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
  Start-Sleep -Seconds 5
}
Run $ollama @("pull", $Model)

# 4 ---------------------------------------------------------------- index
Step "4/5 The law index"
if (Test-Path "data\index\index.json") {
  Write-Host "Found data\index; keeping it."
} else {
  if ($Index -eq "ask") {
    if ($IndexRepo) { $Index = "download" }
    else {
      Write-Host "There is no law index on this computer yet. Choose one:"
      Write-Host "  1  Starter: the 11 Acts everyday questions rely on (Penal Code, Labour Act, dowry,"
      Write-Host "     women and children, consumer rights, rent, contract, Constitution...). About 30 minutes."
      Write-Host "  2  Full: every Act in force on bdlaws.minlaw.gov.bd. Many hours on a laptop; leave it overnight."
      Write-Host "  3  Download a prebuilt index from a Hugging Face dataset (you need its name)."
      $choice = Read-Host "Type 1, 2 or 3 and press Enter [1]"
      $Index = @{ "" = "starter"; "1" = "starter"; "2" = "full"; "3" = "download" }[$choice.Trim()]
      if (-not $Index) { $Index = "starter" }
    }
  }
  switch ($Index) {
    "download" {
      if (-not $IndexRepo) { $IndexRepo = Read-Host "Dataset name, for example someone/bdrag-index" }
      Run $Py @("-m", "rag.cli", "sync", "pull", "--repo", $IndexRepo)
    }
    "starter" {
      $ids = & $Py -c "from rag.topics import TOPICS; print(' '.join(str(i) for i in sorted({a.act_id for t in TOPICS for a in t.acts if a.act_id})))"
      Run $Py (@("-m", "rag.cli", "ingest", "--act-ids") + ($ids -split " "))
      Run $Py @("-m", "rag.cli", "index", "--bm25")
    }
    "full" {
      Run $Py @("-m", "rag.cli", "ingest")
      Run $Py @("-m", "rag.cli", "index", "--bm25")
    }
    "skip" { Write-Host "Skipped. bdrag start will tell you what is missing." }
  }
}
# The embedding model the index was built with, so later runs can work offline.
Run $Py @("-c", "import json, pathlib; p = pathlib.Path('data/index/index.json'); m = json.loads(p.read_text(encoding='utf-8')).get('embedder', '') if p.exists() else ''; m.startswith('hashing') or not m or __import__('sentence_transformers').SentenceTransformer(m)")

# 5 ---------------------------------------------------------------- start
Step "5/5 Checks"
$env:RAG_LLM = "ollama"; $env:RAG_MODEL = $Model
& $Py -m rag.cli doctor
Write-Host ""
Write-Host "Setup is done. START_WINDOWS.bat starts the assistant from now on." -ForegroundColor Green
if (-not $NoStart) {
  & $Py -m rag.cli start --model $Model --port $Port
}
