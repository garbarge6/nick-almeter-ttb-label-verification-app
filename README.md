# TTB Label Verification

Phase 0 proves the app can run locally and deploy to one live URL before real label-verification features are added.

## Local setup

Install `uv`, then run:

```powershell
uv sync
uv run pytest
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
```

The frontend should show the JSON response from `/health`.

## Secrets

Copy `.env.example` to `.env` for local values only. Real secrets must stay in environment variables and must never be committed.

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
