# TTB Label Verification

A stateless proof-of-concept for checking alcohol label images against application data. The app extracts label text with a vision model, compares seven fields, and returns a clear `APPROVED` or `NEEDS REVIEW` result with per-field details.

## Live Demo

- Live URL: https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com
- Health check: https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com/health


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

The government warning is checked as an exact, case-sensitive string match after whitespace collapse. Other fields use normalization or fuzzy comparison where appropriate.

## Requirements Covered

- FastAPI backend with Python 3.12
- Plain HTML/CSS/JS frontend
- Vision model extraction with structured output
- Stateless/in-memory processing, no database
- Single-label verification
- Batch upload and verification
- Per-field `PASS` / `FAIL` results
- Overall `APPROVED` / `NEEDS_REVIEW` verdict
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

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | yes | - | Auth for the OpenAI Responses API; read by the OpenAI SDK from the process environment. |
| `VISION_MODEL` | no | `gpt-4o-mini` | Model name for label extraction. |
| `VISION_TIMEOUT_SECONDS` | no | `4` | Per-request timeout on the vision call. |
| `VISION_IMAGE_MAX_SIDE` | no | `1200` | Preprocessing downscale target for the longest image side. |
| `VISION_JPEG_QUALITY` | no | `76` | Preprocessing JPEG quality. |
| `BATCH_MAX_ITEMS` | no | `10` | Per-request batch cap. |
| `BATCH_CONCURRENCY_LIMIT` | no | `3` | Semaphore bound on concurrent vision calls. |
| `APP_ENV` | no | `production` | Reported in `/health` as the runtime environment label. |
| `APP_VERSION` | no | `0.0.1` | Reported in `/health` and FastAPI metadata. |

## Deployment

Recommended path: Render Web Service. The repo includes `render.yaml` so the service can be recreated from source instead of dashboard-only settings.

```text
Runtime: Python
Build command: uv sync --locked --no-dev
Start command: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /health
```

Set `OPENAI_API_KEY` in the host dashboard or Render blueprint secret prompt only. Do not commit `.env`.

Cold-start disclaimer: the committed `render.yaml` uses Render free tier for reproducibility. The latest live run on the active deployment stayed under the 5-second target, and the UI still shows a delayed message after about 3 seconds (`First request after idle can take ~10 s while the server wakes up.`) so reviewers understand any future free-tier wake-up delay as a hosting limitation rather than a broken form.

## API

### `GET /health`

Returns service health JSON.

### `POST /verify`

Multipart form fields:

```text
image: image file selected by the user
application_data: JSON string matching ApplicationData
```

Returns:

```text
verification: per-field results, overall_verdict, and latency_ms
extracted_label: structured extracted fields plus raw_text and extraction_confidence
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
results[] with individual details
```

One bad label does not fail the whole batch; it appears as a failed item in `results[]` while the summary keeps the three spec keys.

## 8. API Examples

Single-label request:

```bash
curl -X POST https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com/verify \
  -F "image=@samples/sample-label.png" \
  -F 'application_data={"brand_name":"ACME WINE","class_type":"Cabernet Sauvignon","producer":"Acme Winery LLC","country_of_origin":"USA","abv":"45%","net_contents":"750 mL","government_warning":"GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."}'
```

Single-label expected response shape:

```json
{
  "verification": {
    "overall_verdict": "APPROVED",
    "fields": [
      {
        "field": "brand_name",
        "match_type": "fuzzy",
        "expected": "ACME WINE",
        "found": "acme wine",
        "status": "PASS"
      }
    ],
    "latency_ms": 1234
  },
  "extracted_label": {
    "brand_name": "acme wine",
    "class_type": "cabernet sauvignon",
    "producer": "Acme Winery",
    "country_of_origin": "United States",
    "abv": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750ml",
    "government_warning": "GOVERNMENT WARNING: ...",
    "raw_text": "Visible label text used for extraction",
    "extraction_confidence": 0.97
  },
  "latency_ms": 1234
}
```

Batch request with two labels:

```bash
curl -X POST https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com/verify/batch \
  -F "images=@samples/sample-label.png" \
  -F "images=@samples/sample-label.png" \
  -F 'items=[{"client_id":"label-1","image_index":0,"application_data":{"brand_name":"ACME WINE","class_type":"Cabernet Sauvignon","producer":"Acme Winery LLC","country_of_origin":"USA","abv":"45%","net_contents":"750 mL","government_warning":"GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."}},{"client_id":"label-2","image_index":1,"application_data":{"brand_name":"WRONG BRAND","class_type":"Cabernet Sauvignon","producer":"Acme Winery LLC","country_of_origin":"USA","abv":"45%","net_contents":"750 mL","government_warning":"GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."}}]'
```

Batch expected response shape:

```json
{
  "summary": {
    "passed": 1,
    "needs_review": 1,
    "total": 2
  },
  "results": [
    {
      "client_id": "label-1",
      "filename": "sample-label.png",
      "status": "COMPLETED",
      "verification": {
        "overall_verdict": "APPROVED",
        "fields": [
          {
            "field": "brand_name",
            "match_type": "fuzzy",
            "expected": "ACME WINE",
            "found": "acme wine",
            "status": "PASS"
          }
        ],
        "latency_ms": 1234
      },
      "extracted_label": {
        "raw_text": "Visible label text used for extraction",
        "extraction_confidence": 0.97
      },
      "latency_ms": 1234,
      "error": null
    }
  ]
}
```

Error responses use FastAPI's `detail` wrapper with a stable inner error object:

```json
{
  "detail": {
    "error": {
      "code": "invalid_file_type",
      "message": "Please upload an image file."
    }
  }
}
```

The contract error object is:

```json
{"error":{"code":"invalid_file_type","message":"Please upload an image file."}}
```

## Matching Approach

1. The vision service extracts a structured `ExtractedLabel`.
2. Pydantic validates the output shape.
3. The comparison engine evaluates each field.
4. Any failed field makes the overall verdict `NEEDS_REVIEW`; otherwise the verdict is `APPROVED`.

## Comparison Rules

| Field | Rule |
| --- | --- |
| Brand Name | Fuzzy normalized text comparison with threshold `90.0`. Common legal suffixes such as `LLC`, `Inc`, and `Company` are ignored; short subset traps like `ACME` vs `ACME RESERVE SPECIAL EDITION` fail. |
| Product Class | Fuzzy normalized text comparison with threshold `90.0`. |
| Producer Name | Fuzzy normalized text comparison with threshold `90.0`; common legal suffixes are ignored. |
| Country of Origin | Text is normalized and checked against a small synonym map, e.g. `USA` and `United States` both normalize to `united states`. |
| Alcohol % | Numeric percent comparison with tolerance `+/- 0.1`; proof text is converted to ABV, so `90 Proof` becomes `45.0`. |
| Bottle Size | Unit-normalized milliliter comparison with tolerance `+/- 1 mL`; `0.75 L`, `75 cl`, and `750 ml` normalize to the same value. |
| Government Warning | Exact, case-sensitive string comparison after whitespace collapse. No punctuation, capitalization, or missing-word correction is applied. |

## Tools Used

- FastAPI for API and static frontend serving
- Pydantic for typed request/response models
- Pillow for image preprocessing
- OpenAI Responses API for vision extraction with structured output
- uv for dependency management
- pytest for automated tests

## Approach / Tools

The project was built with an AI-native Plan / Review / Execute cadence using Codex as the coding assistant.

- **Plan:** Codex helped turn the phase requirements into scoped implementation steps, file lists, risks, and verification checks before code changes.
- **Review:** Codex critiqued plans against hard requirements such as batch upload, the under-5-second target, exact government-warning matching, no database, and environment-only secrets. The human reviewer called out contract drift, accessibility gaps, and README gaps; those review notes overrode convenience choices.
- **Execute:** Codex made the code and documentation edits, added tests, and ran the local pytest suite. The comparison logic, API DTOs, frontend rendering, and README examples were hand-checked against the stated spec after generation.
- **Human overrides:** The reviewer explicitly tightened response-contract literals, required schema-lock tests, required batch upload as non-optional, and required usability/accessibility fixes. Those corrections changed earlier AI-generated assumptions such as using `PASS` as an overall verdict and exposing extra batch summary keys.
- **Hand-written pieces:** The final project structure, test assertions, prompt constraints, API contract mapping, and deployment notes were edited directly in the repo and verified with local tests rather than accepted solely from generated text.

## Assumptions

- The user provides application data manually for each label.
- The uploaded file is an image that Pillow and the vision model can read after preprocessing.
- The deployed environment supplies `OPENAI_API_KEY` and any optional runtime overrides as environment variables.
- The user is checking TTB-style alcohol labels with the seven fields listed above.
- Batch requests are independent; there is no saved history or cross-request state.

## Limitations

- Vision extraction can misread blurry, angled, cropped, low-resolution, or glare-heavy images.
- Exact warning comparison may fail if OCR misses a colon, capital letter, punctuation mark, or word.
- Free-tier hosting can cold start, which may exceed the 5-second target even when warm requests are faster; the UI warns after a few seconds, and strict compliance needs non-sleeping hosting.
- Batch progress is request-level, not live per-item streaming.
- No database, saved history, user accounts, audit trail, or manual review queue is included.

## Tradeoffs

- The fuzzy threshold is fixed at `90.0`: high enough to avoid many false approvals, but conservative labels may still require review.
- Batch size is capped at `10` uploaded images and `10` JSON items to limit memory, vision API cost, timeout risk, and free-tier resource spikes.
- Batch concurrency defaults to `3` to improve throughput without launching every vision request at once.
- The API keeps failed batch items in `results[]` instead of adding extra summary keys, so the summary remains the spec shape `{passed, needs_review, total}`.
- The frontend is plain HTML/CSS/JavaScript to reduce deployment complexity; it gives up richer framework tooling.

## Performance Notes

Current preprocessing defaults:

```text
max side: 1200 px
JPEG quality: 76
model: gpt-4o-mini
single-label timeout: 4 seconds
```

Local preprocessing measurement on committed `samples/sample-label.png` during hardening:

```text
original bytes: 60,666
processed size: 1200 x 800
processed bytes median: 58,868
```

Live single-label latency should be measured after deployment with at least 20 runs so p95 is meaningful:

```powershell
uv run python scripts/run_phase6_live_checklist.py https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com samples/sample-label.png --runs 20
```

Latest 20-run Render measurement, recorded July 15, 2026:

```text
runs: 20
wall p50: 2853 ms
wall p95: 3562 ms
wall max: 3797 ms
API p50: 2510 ms
API p95: 3107 ms
under 5000 ms target: true
```

The latest live run on the active Render deployment meets the under-5-second gate and confirms that `/verify/batch` returns the corrected summary contract.
## Test Images

The repo includes `samples/sample-label.png` as a simple synthetic smoke-test image. It is not official TTB data.

Use your own real label image for live performance and extraction checks.

## Verification Results

Automated local tests:

```text
uv run pytest
59 passed, 1 warning
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
batch summary: total 3, passed 1, needs_review 1
```

Live checklist against Render:

```text
Live URL: https://nick-almeter-ttb-label-verification-app-tjj2.onrender.com
Recorded: July 15, 2026
Single-label runs, wall ms: 3550, 2486, 3095, 2444, 3140, 3214, 2775, 2822, 3797, 2897, 3458, 3127, 2733, 3084, 2522, 2752, 2760, 2767, 2883, 2616
Single-label p50 wall ms: 2853
Single-label p95 wall ms: 3562
Single-label max wall ms: 3797
API latency ms: 3123, 2195, 2693, 2188, 2878, 2744, 2499, 2348, 3106, 2211, 2657, 2765, 2443, 2793, 2187, 2424, 2520, 2497, 2587, 2360
API p50 ms: 2510
API p95 ms: 3107
p95 under 5000 ms: true
All runs under 5000 ms: true
Mismatch: 200, 2656 ms, NEEDS_REVIEW
Imperfect image: 200, 2615 ms, NEEDS_REVIEW
Wrong file type: 400, readable invalid_file_type error
Empty submit: 422, readable invalid_request error
Batch response shape from live deployment: summary keys are needs_review, passed, total; summary_contract_ok is true.
```

Performance/deployment note: the latest 20-run live sample meets the strict under-5-second gate, and the live batch endpoint is serving the corrected summary contract.

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




