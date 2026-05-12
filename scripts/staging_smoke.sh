#!/usr/bin/env bash
# 中文：staging smoke check，验证生产 compose API 健康、场景创建和场景运行。
# English: Staging smoke check validating production-compose API health, scenario creation, and scenario execution.

set -euo pipefail

base_url="${ORIGAMI_API_BASE_URL:-http://127.0.0.1:8000}"
api_token="${ORIGAMI_API_TOKEN:?Set ORIGAMI_API_TOKEN for staging smoke}"
python_bin="${PYTHON:-python3}"
scenario_id="staging_smoke_$(date -u +%Y%m%d%H%M%S)"

for _ in $(seq 1 30); do
  if curl -fsS "${base_url}/api/health" >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS "${base_url}/api/health" >/dev/null
curl -fsS -H "X-Origami-Token: ${api_token}" "${base_url}/api/runtime-config" >/dev/null

curl -fsS \
  -H "X-Origami-Token: ${api_token}" \
  -H "Content-Type: application/json" \
  -X POST "${base_url}/api/scenarios" \
  -d "{
    \"id\": \"${scenario_id}\",
    \"name\": \"Staging Smoke\",
    \"tags\": [\"staging\", \"smoke\"],
    \"observation\": {
      \"position\": [0, 0],
      \"target\": [1, 0],
      \"payload_kg\": 2.0,
      \"payload_locked\": true,
      \"battery_pct\": 80.0,
      \"nearest_human_distance_m\": 2.0,
      \"fleet_context\": {\"nearby_robots\": 0}
    },
    \"expected\": {
      \"final_move\": \"east\",
      \"seom_passed\": true
    }
  }" >/dev/null

run_payload="$(
  curl -fsS \
    -H "X-Origami-Token: ${api_token}" \
    -X POST "${base_url}/runs/scenario/${scenario_id}"
)"

echo "${run_payload}" | "${python_bin}" -c 'import json, sys; payload = json.load(sys.stdin); assert payload["quality_gate_passed"] is True'
