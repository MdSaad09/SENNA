from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    
    return {
        "status": "ok",
        "model_version": getattr(request.app.state, "model_version", None),
    }
