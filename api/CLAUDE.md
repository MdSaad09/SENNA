# api/ — the serving layer

- Training never happens here, and WANDB_API_KEY never appears here (F-26). The API
  loads a frozen model triplet — weights + vecnormalize.pkl + SHAP surrogate — from
  /app/models; MODEL_VERSION selects it.
- There is no queue and no worker on this branch. `POST /simulations` races the run to
  completion on a thread (`run_in_threadpool`) and answers when it is finished — about
  eighteen seconds for a grand prix. The event loop must never do the racing itself.
- The runner lives in `senna/serve/runner.py`, not in the API. It is research code — the
  episode loop, the decision cards, the SHAP explainers — and the API is one caller of
  it. Keep it that way: anything that simulates belongs in the package.
- There is no cache, so E-15's stale-key hazard cannot occur. `env_config_hash` is still
  written to the run row, as provenance rather than as a key.
- Streaming is gone with the WebSocket. Clients read stored frames over HTTP; playback is
  the reader's problem, not the server's.
- Response shapes are the 5.9.2 Pydantic models — change the spec before changing a
  shape. `CircuitDetail` is the one deliberate divergence: the ribbon pipeline is not on
  this branch, so it carries fit coverage instead of geometry.
- No client-reachable URL may be a Docker hostname (F-27). Streamlit reaches the API
  through SENNA_API_BASE, which is a server-side value — the browser only ever talks to
  Streamlit.
