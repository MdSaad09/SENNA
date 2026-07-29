#!/usr/bin/env bash
# Warm the 5.13 demo runs against the local stack (`make up` first). A cold deep link
# blocks until the whole simulation completes (api/ws.py waits on status=complete), so
# the recruiter beat only holds against a run that already exists. E-15 keeps the warm
# honest: the warmed run IS the run the link resolves to — same model version, same
# config hash, same request fields, same cache key.
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
FRONTEND="${FRONTEND:-http://localhost:5173}"
# stylised — the 5.13 demo pick (F15 plan): Bahrain has a committed ribbon, native
# 2024 fits, an ASCII slug, and the real 2024 winner pitted on lap 18 — the
# storyboard's own beat. These values must match frontend/e2e/demo.spec.ts and
# docs/demo/script.md; change all three together or the check measures a cold link.
CIRCUIT="${CIRCUIT:-bahrain_grand_prix}"
SEED="${SEED:-42}"
GRID="${GRID:-8}"  # DEFAULT_GRID_POSITION — what the deep link sends when ?grid= is absent

json_field() {
  python3 -c "import json, sys; print(json.load(sys.stdin)[\"$1\"])"
}

echo "warming the live run: $CIRCUIT seed $SEED grid $GRID"
RUN=$(curl -sf -X POST "$API/simulations" -H 'content-type: application/json' \
  -d "{\"circuit_id\": \"$CIRCUIT\", \"grid_position\": $GRID, \"seed\": $SEED}" \
  | json_field run_id)

echo "warming the counterfactual pair: 2024 round 1 VER seed $SEED"
CF=$(curl -sf -X POST "$API/counterfactuals" -H 'content-type: application/json' \
  -d "{\"year\": 2024, \"round\": 1, \"driver\": \"VER\", \"seed\": $SEED}" \
  | json_field run_id)

for id in "$RUN" "$CF"; do
  printf 'run %s ' "$id"
  until [ "$(curl -sf "$API/simulations/$id" | json_field status)" = complete ]; do
    printf '.'
    sleep 2  # operational — a full sim takes tens of seconds; 2 s keeps the dots honest without hammering the API
  done
  echo ' complete'
done

echo
echo "demo deep link:  $FRONTEND/live?circuit=$CIRCUIT&seed=$SEED&lap=18&speed=30&year=2024&round=1&driver=VER"
echo "counterfactual:  $FRONTEND/counterfactual?year=2024&round=1&driver=VER&seed=$SEED"
