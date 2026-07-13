import logging

logger = logging.getLogger(__name__)


def log_verify_finished(
    *,
    latency_ms: int,
    verdict: str | None = None,
    error_code: str | None = None,
    failures: list[str] | None = None,
) -> None:
    if error_code:
        logger.warning(
            "verify_failed",
            extra={"latency_ms": latency_ms, "error_code": error_code},
        )
        return

    logger.info(
        "verify_completed",
        extra={
            "latency_ms": latency_ms,
            "verdict": verdict,
            "field_failures": failures or [],
        },
    )


def log_batch_finished(*, latency_ms: int, total: int, passed: int, needs_review: int) -> None:
    logger.info(
        "verify_batch_completed",
        extra={
            "latency_ms": latency_ms,
            "total": total,
            "passed": passed,
            "needs_review": needs_review,
        },
    )


def log_exception_details(error_code: str, latency_ms: int, exc: Exception) -> None:
    logger.exception(
        "verify_exception",
        extra={"latency_ms": latency_ms, "error_code": error_code},
    )
