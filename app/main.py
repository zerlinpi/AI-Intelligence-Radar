from fastapi import FastAPI

from app.pipeline import run_daily_radar

app = FastAPI(title="AI Intelligence Radar")


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
