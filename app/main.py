import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.verify import router as verify_router


APP_ENV = os.getenv("APP_ENV", "production")
APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="TTB Label Verification", version=APP_VERSION)
app.include_router(verify_router)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request
    missing_fields = {str(error.get("loc", [""])[-1]) for error in exc.errors()}

    if "image" in missing_fields:
        message = "Please choose a label image."
    elif "application_data" in missing_fields:
        message = "Please fill in all fields before checking the label."
    else:
        message = "Please check the form and try again."

    return JSONResponse(
        status_code=422,
        content={"detail": {"error": {"code": "invalid_request", "message": message}}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ttb-label-verification",
        "version": APP_VERSION,
        "environment": APP_ENV,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")