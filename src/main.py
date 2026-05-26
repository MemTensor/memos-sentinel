"""MemOS Sentinel — PR & Issues Orchestrator Agent."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.webhook import router as webhook_router
from src.web.confirm import router as confirm_router
from src.web.dashboard import router as dashboard_router
from src.scheduler.cron import start_scheduler

app = FastAPI(
    title="MemOS Sentinel",
    description="Orchestrator Agent for MemTensor/MemOS issue & PR management",
    version="0.2.0",
)

app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
app.include_router(confirm_router, prefix="/confirm", tags=["confirm"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])


@app.on_event("startup")
async def on_startup():
    from src.store.db import init_db
    from src.agent.graph import setup_langsmith

    await init_db()
    setup_langsmith()
    start_scheduler()


@app.get("/health")
async def health():
    from src.tools.github_client import get_rate_limit_status

    rl = get_rate_limit_status()
    return {
        "status": "ok",
        "service": "memos-sentinel",
        "version": "0.3.0",
        "github_rate_limit_remaining": rl["remaining"],
        "github_rate_limit_resets_in": rl["resets_in"],
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger(__name__).error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})
