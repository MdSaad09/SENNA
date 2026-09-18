

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import routes
from api.deps import serving_config
from senna.data.db import database_url, engine_for
from senna.serve.loader import read_manifest


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    app.state.model_version = read_manifest(
        version=os.environ.get("MODEL_VERSION")
    )["model_version"]
    app.state.engine = engine_for(database_url())
    try:
        yield
    finally:
        await app.state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="SENNA API", lifespan=lifespan)

    origins = list(serving_config()["cors"]["allow_origins"])
    if os.environ.get("CORS_ORIGIN"):  # the production frontend origin (5.11.2)
        origins.append(os.environ["CORS_ORIGIN"])
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def stamp_model_version(request, call_next):
        response = await call_next(request)
        response.headers["X-Model-Version"] = getattr(
            request.app.state, "model_version", "unset"
        )
        return response

    for router in routes.ALL:
        app.include_router(router, prefix="/api/v1")

    return app


app = create_app()
