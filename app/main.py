from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.pipeline import run_daily_radar
from app.scheduler import start_scheduler, stop_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="AI Intelligence Radar",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "name": "AI Intelligence Radar",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "ok": True,
        "scheduler": scheduler.running,
    }


@app.get("/ready")
def readiness_check():
    ready = bool(scheduler.running)
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "ready": ready,
            "scheduler": ready,
        },
    )


@app.post("/run")
def run():
    return run_daily_radar()
