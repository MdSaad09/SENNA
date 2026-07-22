"""The SENNA API (5.9.2). The lifespan owns the async engine, the redis client and
the RQ handle; simulations run in the worker, never here (F-26) — the event loop
belongs to the WebSocket. Every response carries X-Model-Version (5.11.2) without
touching a 5.9.2 body shape, errors included: a version-less 404 is still an answer
someone will screenshot.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import redis
import redis.asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rq import Queue

from api import routes, ws
from api.deps import redis_url, serving_config
from senna import config
from senna.data.db import database_url, engine_for
from senna.serve.loader import read_manifest


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MODEL_VERSION selects the baked triplet (5.11.2, F-26); unset and the local
    # alias dev-latest both mean the promoted headline, and a version this image
    # does not bake fails loudly at startup, never silently falls back
    app.state.model_version = read_manifest(
        version=os.environ.get("MODEL_VERSION")
    )["model_version"]
    app.state.engine = engine_for(database_url())
    app.state.redis = redis.asyncio.from_url(redis_url(), decode_responses=True)
    rq_conn = redis.Redis.from_url(redis_url())
    app.state.queue = Queue(serving_config()["queue"]["name"], connection=rq_conn)
    app.state.playback_sleep = asyncio.sleep  # tests swap in a recorder (E-16 clock)
    try:
        yield
    finally:
        await app.state.engine.dispose()
        await app.state.redis.aclose()
        rq_conn.close()


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
    app.include_router(ws.router)

    ribbons = config.REPO_ROOT / "data" / "circuits"
    if ribbons.is_dir():
        # CircuitDetail.gltf_url points here, relative on purpose (F-27)
        app.mount("/api/v1/assets/circuits", StaticFiles(directory=ribbons))

    return app


app = create_app()
