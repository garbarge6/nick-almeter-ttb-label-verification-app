# TTB Label Verification

Phase 0 proves the app can run locally and deploy to one live URL before real label-verification features are added.

## Local setup

Install `uv`, then run:

```powershell
uv sync
uv run python -m pytest
uv run python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
```

The frontend should show the JSON response from `/health`.

## Secrets

Copy `.env.example` to `.env` for local values only. Real secrets must stay in environment variables and must never be committed.

## Vision sample

After setting `OPENAI_API_KEY` in your environment, run the vision extractor against a local label image:

```powershell
$env:OPENAI_API_KEY = (Get-Content .env | Where-Object { $_ -match '^OPENAI_API_KEY=' } | ForEach-Object { ($_ -split '=', 2)[1].Trim() })
uv run python scripts/run_vision_sample.py images\jim.png
```

For an offline smoke check that does not call the API:

```powershell
uv run python scripts/run_vision_sample.py images\jim.png --fake
```
## Batch verification

The frontend includes Single Label and Batch modes. Batch mode sends multiple labels to:

```text
POST /verify/batch
```

Batch settings:

```text
BATCH_MAX_ITEMS=10
BATCH_CONCURRENCY_LIMIT=3
```

Each label gets its own result. One bad label does not fail the whole batch.
## Render deploy

Create a Render Web Service from this repo.

```text
Runtime: Python
Instance type: Free
Build command: uv sync --locked --no-dev
Start command: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /health
```

Set production environment values in Render only:

```text
APP_ENV=production
APP_VERSION=0.0.1
```

After deploy, verify:

```text
https://<service>.onrender.com/
https://<service>.onrender.com/health
```

Exit check: the frontend loads at the live URL and displays the `/health` JSON response.
