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
    version="0.1.0",
)

app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
app.include_router(confirm_router, prefix="/confirm", tags=["confirm"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])


@app.on_event("startup")
async def on_startup():
    from src.store.db import init_db

    await init_db()
    start_scheduler()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "memos-sentinel"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})
