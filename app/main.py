from fastapi import FastAPI

app = FastAPI(title="AI Intelligence Radar")


@app.get("/")
def health():
    return {
        "name": "AI Intelligence Radar",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {"ok": True}
