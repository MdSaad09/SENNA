# api/ and worker/ — the serving layer

- Training never happens here, and WANDB_API_KEY never appears here (F-26). The worker
  loads a frozen model triplet — weights + vecnormalize.pkl + SHAP surrogate — baked
  into the image at /app/models; MODEL_VERSION selects it.
- Simulations run in the RQ worker, never in a request handler or BackgroundTask — the
  event loop belongs to the WebSocket (F-26).
- Streaming reads stored frames on a playback clock; the socket is a view over
  Postgres/Redis state, so reconnect and scrub are reads, never re-simulations (E-16).
- Every cache key includes model_version and env_config_hash (E-15).
- Response shapes are the 5.9.2 Pydantic models — change the spec before changing a
  shape.
- No client-reachable URL may be a Docker hostname; browser config comes from VITE_*
  build-time variables per 5.11.2 (F-27), wss:// in production.
