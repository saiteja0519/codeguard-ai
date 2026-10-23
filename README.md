# CodeGuard AI

AI-assisted GitHub repository/code review MVP with a React + TypeScript dashboard and FastAPI backend. It supports public GitHub repositories, pasted code, source-file/ZIP uploads, heuristic static checks, optional OpenAI/Anthropic review, JSON report export, and optional AI fix proposals for pasted code.

> Security note: this is a portfolio-grade MVP, not a hardened multi-tenant production service. Do not expose it publicly without adding authentication, durable job storage, stricter network egress controls, deployment secrets management, and additional security review. Repository code is never executed by this app. Python fix validation checks syntax only; it does not prove correctness.

## Features

- Public GitHub repo ingestion through GitHub REST API; optional `GITHUB_TOKEN` for rate limits/authorized private repositories.
- Upload a UTF-8 source file or ZIP archive with file-count and size limits, path traversal filtering, and supported-extension allowlisting.
- Paste code, specify a filename, and describe the observed bug.
- Python AST checks: syntax errors, `eval`/`exec`, bare `except`, mutable defaults, division by `len(...)`, and redundant boolean comparisons.
- Heuristic checks for possible hard-coded secrets, `eval`, SQL concatenation, debug logs, and TODO/FIXME markers in other supported languages.
- Optional AI review and patch generation using OpenAI or Anthropic.
- Findings severity, category, confidence, evidence, recommendation, and report export.
- Responsive React dashboard with filters and proposed patch display.

## Requirements

- Python 3.12 recommended
- Node.js 20+ and npm
- Optional AI provider key for AI review/fix generation

## Run backend (Windows PowerShell)

```powershell
cd codeguard-ai\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env if you want AI review or a GitHub token
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or run `.\run.ps1` from the backend directory after reviewing it.

## Run backend (Linux/macOS)

```bash
cd codeguard-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs
Health check: http://127.0.0.1:8000/health

## Run frontend

In another terminal:

```bash
cd codeguard-ai/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. To use a different backend URL, create `frontend/.env` with `VITE_API_BASE_URL=http://127.0.0.1:8000`.

## Configure AI

Edit `backend/.env`:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=replace-with-your-key
OPENAI_MODEL=gpt-4.1-mini
```

Or use Anthropic:

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=replace-with-your-key
ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

Keep `AI_PROVIDER=none` to use deterministic local heuristics without sending code to an AI provider. Never commit `.env` or credentials. Review your provider's data-handling terms before sending proprietary source code.

For GitHub rate limits, set `GITHUB_TOKEN` to a least-privilege token. Avoid broad permissions. The public repository flow uses the GitHub API and does not clone or execute repositories.

## Run backend tests

```powershell
cd codeguard-ai\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## API examples

### Paste code

```powershell
$body = @{ code = "def average(numbers):`n    return sum(numbers) / len(numbers)`n`nprint(average([]))"; filename = "main.py"; language = "python"; bug_description = "Why does empty input fail?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/analyses/code -Method Post -ContentType 'application/json' -Body $body
```

### Analyze GitHub repo

```powershell
$body = @{ repository_url = 'https://github.com/psf/requests'; max_files = 20 } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/analyses/github -Method Post -ContentType 'application/json' -Body $body
```

### Upload a file

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/analyses/upload -F "file=@.\main.py"
```

## Current limitations

- This MVP does not include user authentication, a database, persistent analysis history, background workers, or pull-request creation.
- AI review analyzes up to 12 selected files with bounded content length; it is not a complete whole-repository semantic index.
- Non-Python checks are conservative regex heuristics and can produce false positives/negatives.
- The generated fix endpoint accepts source code and a finding. The current UI exposes this action for pasted code; repository/upload findings can be inspected and exported but are not yet wired to original source retrieval in the UI.
- Fix validation only parses Python syntax. It does not execute tests or prove semantic correctness.
- The app does not execute any submitted repository code. Do not add arbitrary command execution without a dedicated, hardened sandbox.

## Suggested next steps

1. Add authentication and per-user authorization.
2. Add PostgreSQL persistence and background job queue for large repositories.
3. Add a dedicated isolated validation worker with no network by default.
4. Integrate language-specific tools (Ruff, Bandit, ESLint, Semgrep) as optional, explicitly configured analyzers.
5. Add integration tests and CI, then deploy behind HTTPS with strict request limits and monitoring.
