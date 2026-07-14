from fastapi import FastAPI

app = FastAPI(title="SENNA API")


@app.get("/api/v1/health")
def health():
    # 5.9.2 response shape from day one; model_version stays null until F10
    # bakes the first frozen model triplet into the worker image
    return {"status": "ok", "model_version": None}
