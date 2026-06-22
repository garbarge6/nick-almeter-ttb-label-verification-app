import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.verify import router as verify_router


APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="TTB Label Verification", version=APP_VERSION)
app.include_router(verify_router)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ttb-label-verification",
        "version": APP_VERSION,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")