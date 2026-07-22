from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    # 5.9.2 shape; the version is read off the baked manifest at startup (F-26)
    return {"status": "ok", "model_version": request.app.state.model_version}
