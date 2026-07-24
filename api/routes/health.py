from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    # 5.9.2 shape; the version is read off the baked manifest at startup (F-26). A
    # liveness probe must answer before the model loads and without Postgres or Redis,
    # so read state defensively — null until the lifespan sets it, exactly as the
    # X-Model-Version middleware already does (main.py). The schema allows str | None.
    return {
        "status": "ok",
        "model_version": getattr(request.app.state, "model_version", None),
    }
