#!/usr/bin/env bash
# Test 2: revision switch time. Change REV_MARKER env, measure from apply
# start until the newest revision holds 100% traffic weight and is Running.
set -u
RG=rg-felis-ephem-verify-183
APP=ca-felis-ephem-verify-183

measure() {
  local marker="$1"
  local t0 t1 apply_end newest weight running latest_rev
  t0=$(date +%s.%N)
  echo "----- iteration marker=$marker  apply_start=$(date -u +%Y-%m-%dT%H:%M:%SZ) -----"
  az containerapp update -g "$RG" -n "$APP" --set-env-vars "REV_MARKER=$marker" -o none 2>/dev/null
  apply_end=$(date +%s.%N)
  echo "  az update command returned after $(echo "$apply_end - $t0" | bc)s"
  # newest revision (by createdTime): wait until it holds 100% traffic weight and is running
  while true; do
    mapfile -t vals < <(az containerapp revision list -g "$RG" -n "$APP" \
      --query "sort_by([].{n:name,c:properties.createdTime,w:properties.trafficWeight,r:properties.runningState}, &c)[-1].[n,w,r]" \
      -o tsv 2>/dev/null)
    latest_rev="${vals[0]:-}"; weight="${vals[1]:-}"; running="${vals[2]:-}"
    if [ "$weight" = "100" ] && { [ "$running" = "Running" ] || [ "$running" = "RunningAtMaxScale" ]; }; then
      t1=$(date +%s.%N)
      echo "  NEW REVISION $latest_rev reached 100% traffic (runningState=$running)"
      echo "  >>> time_from_apply_start_to_100pct = $(echo "$t1 - $t0" | bc)s"
      break
    fi
    sleep 1
  done
}

for m in s5 s6 s7 s8; do
  measure "$m"
done
echo "===== revision list (final) ====="
az containerapp revision list -g "$RG" -n "$APP" \
  --query "sort_by([].{name:name,created:properties.createdTime,active:properties.active,running:properties.runningState,replicas:properties.replicas}, &created)" -o table 2>/dev/null
