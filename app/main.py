from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.pipeline import run_daily_radar
from app.scheduler import start_scheduler, stop_scheduler


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
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {"ok": True}


@app.post("/run")
def run():
    return run_daily_radar()
