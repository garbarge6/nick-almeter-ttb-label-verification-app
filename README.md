# TTB Label Verification

A stateless proof-of-concept for checking alcohol label images against application data. The app extracts label text with a vision model, compares seven fields, and returns a clear `APPROVED` or `NEEDS REVIEW` result with per-field details.

## Live Demo

- Live URL: https://nick-almeter-ttb-label-verification-app.onrender.com
- Health check: https://nick-almeter-ttb-label-verification-app.onrender.com/health

Do not submit until the live URL is filled in and the live checklist below has been run.

## How To Use The App

1. Open the live URL.
2. Choose **Single Label** or **Batch**.
3. Upload label image(s).
4. Fill in all application fields.
5. Click **CHECK LABEL** or **CHECK ALL LABELS**.
6. Review the verdict and field details.

For failures, the UI shows what the application says and what the label says.

## What This App Does

The app verifies these seven fields:

- Brand Name
- Product Class
- Producer Name
- Country of Origin
- Alcohol %
- Bottle Size
- Government Warning

The government warning is checked as an exact, case-sensitive string match. Other fields use normalization or fuzzy comparison where appropriate.

## Requirements Covered

- FastAPI backend with Python 3.12
- Plain HTML/CSS/JS frontend
- Vision model extraction with structured output
- Stateless/in-memory processing, no database
- Single-label verification
- Batch upload and verification
- Per-field `PASS` / `FAIL` results
- Overall `PASS` / `NEEDS_REVIEW` verdict
- Exact case-sensitive government warning comparison
- Fuzzy brand/product/producer comparison
- Country synonym normalization
- ABV numeric normalization
- Bottle-size unit normalization
- API keys from environment variables only

## Tech Stack

- Python 3.12
- FastAPI
- Pydantic
- Pillow
- OpenAI Responses API with structured outputs
- Plain HTML/CSS/JavaScript
- uv
- pytest

## Local Setup

Install `uv`, then sync dependencies:

```powershell
uv sync
```

Create a local `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Add your local API key to `.env`:

```text
OPENAI_API_KEY=...
```

`.env` is ignored by git and must not be committed.

## Run Locally

Load the API key into the server process, then start FastAPI:

```powershell
$env:OPENAI_API_KEY = (Get-Content .env | Where-Object { $_ -match '^OPENAI_API_KEY=' } | ForEach-Object { ($_ -split '=', 2)[1].Trim() })
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Run Tests

```powershell
uv run pytest
```

If the Windows console-script path gets stale, use:

```powershell
uv run python -m pytest
```

## Environment Variables

```text
OPENAI_API_KEY=required in local/deployed environment
APP_ENV=production
APP_VERSION=0.0.1
VISION_MODEL=gpt-4o-mini
VISION_TIMEOUT_SECONDS=4
VISION_IMAGE_MAX_SIDE=1200
VISION_JPEG_QUALITY=76
BATCH_MAX_ITEMS=10
BATCH_CONCURRENCY_LIMIT=3
```

## Deployment

Recommended free-tier path: Render Web Service.

```text
Runtime: Python
Build command: uv sync --locked --no-dev
Start command: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /health
```

Set environment variables in the host dashboard only. Do not commit `.env`.

## API

### `GET /health`

Returns service health JSON.

### `POST /verify`

Multipart form fields:

```text
image: PNG, JPG, or WebP label image
application_data: JSON string matching ApplicationData
```

Returns:

```text
verification: per-field results and verdict
extracted_label: structured extracted fields
latency_ms: endpoint latency
```

### `POST /verify/batch`

Multipart form fields:

```text
images: one or more uploaded files
items: JSON array mapping each item to an image_index and application_data
```

Batch response includes:

```text
summary.total
summary.passed
summary.needs_review
summary.failed_to_process
results[] with individual details
```

One bad label does not fail the whole batch.

## Matching Approach

1. The vision service extracts a structured `ExtractedLabel`.
2. Pydantic validates the output shape.
3. The comparison engine evaluates each field.
4. Any failed field makes the overall verdict `NEEDS_REVIEW`.

Field strategies:

```text
Brand/Product/Producer: fuzzy normalized text
Country: synonym normalization
ABV: numeric percent normalization
Bottle Size: unit normalization to milliliters
Government Warning: exact case-sensitive string match
```

## Tools Used

- FastAPI for API and static frontend serving
- Pydantic for typed request/response models
- Pillow for image preprocessing
- OpenAI Responses API for vision extraction with structured output
- uv for dependency management
- pytest for automated tests

## Assumptions

- The user provides application data manually.
- Label images are PNG, JPG, or WebP.
- Government warning text must match exactly, including capitalization and punctuation.
- Batch size is capped at 10 labels.
- Batch processing is concurrent but bounded to control API cost/rate risk.

## Limitations

- Vision extraction can misread blurry, angled, cropped, or glare-heavy images.
- Exact warning comparison may fail if OCR misses a colon, capital letter, or punctuation mark.
- Free-tier hosting can cold start, which may exceed the 5-second target.
- Batch progress is request-level, not live per-item streaming.
- No database, saved history, user accounts, or audit trail.

## Performance Notes

Current preprocessing defaults:

```text
max side: 1200 px
JPEG quality: 76
model: gpt-4o-mini
single-label timeout: 4 seconds
```

Local preprocessing measurement on `images/jim.png` during hardening:

```text
original bytes: 2,639,566
processed size: 1200 x 840
processed bytes median: 202,986
```

Live single-label latency must be measured after deployment with:

```powershell
uv run python scripts/run_phase6_live_checklist.py https://nick-almeter-ttb-label-verification-app.onrender.com path\to\sample-label.png --runs 3
```

## Test Images

The repo includes `samples/sample-label.png` as a simple synthetic smoke-test image. It is not official TTB data.

Use your own real label image for live performance and extraction checks.

## Verification Results

Automated local tests:

```text
uv run pytest
49 passed, 1 warning
```

Local mocked checklist:

```text
valid label: PASS
mismatch: NEEDS_REVIEW
case-only brand difference: PASS
missing warning: NEEDS_REVIEW
wrong-caps warning: NEEDS_REVIEW
correct exact warning: PASS
wrong file type: readable 400
empty submit: readable 422
batch summary: total 3, passed 1, needs_review 1, failed_to_process 1
```

Live checklist against Render:

```text
Live URL: https://nick-almeter-ttb-label-verification-app.onrender.com
Single-label runs, wall ms: 11099, 4084, 4667
Single-label p50 wall ms: 4667
Single-label max wall ms: 11099
API latency ms: 9248, 3369, 4010
Single-label verdicts: NEEDS_REVIEW, NEEDS_REVIEW, NEEDS_REVIEW
Under 5000 ms for all runs: false
Mismatch: 200, NEEDS_REVIEW, 8337 ms
Imperfect image: 200, NEEDS_REVIEW, 3451 ms
Wrong file type: 400, readable invalid_file_type error
Empty submit: 422, readable invalid_request error
Batch summary: total 3, passed 0, needs_review 2, failed_to_process 1, latency 5154 ms
```

Performance note: two warm single-label runs completed under 5 seconds, but the first run took 11.1 seconds. The strict under-5-second gate is not fully demonstrated on Render yet, likely due to cold start and/or first vision request overhead.

## Security

- Secrets are read from environment variables.
- `.env` is ignored and must not be committed.
- `.env.example` contains placeholders only.
- Debug logs are ignored.
- No database is used.

## Pre-Submission Audit

Run before making the repo public:

```powershell
uv run pytest
git status --short
git check-ignore .env
git ls-files .env
git diff --cached --name-only
git diff --cached --name-only | Select-String -Pattern '(^|/)\.env$|\.env\.'
git diff --cached | Select-String -Pattern 'sk-|OPENAI_API_KEY=sk|api[_-]?key\s*=|secret\s*=|token\s*=|password\s*='
rg -n --hidden --glob '!.git/**' --glob '!logs/**' --glob '!.venv/**' --glob '!.env' --glob '!.env.*' "sk-|OPENAI_API_KEY=sk|api[_-]?key\s*=|secret\s*=|token\s*=|password\s*=" .
rg -n "YOUR-LIVE-URL|<service>|TODO|TBD" README.md
```

Expected results:

```text
tests pass
.env is ignored
.env is not tracked
no staged env files
no staged secret patterns
secret grep has no real secrets; code references to api_key are allowed
README has no placeholders before final submission
```