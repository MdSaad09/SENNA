"""MaskablePPO training with the 5.7 competence-gated curriculum (F07). Pure gate
decisions live in gates.py so hand-built histories can test them; everything that rolls
episodes lives in evals.py; wandb touches tracking.py only (F-26)."""
