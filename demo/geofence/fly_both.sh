#!/usr/bin/env bash
# Fly M02 twice through the whole pipeline: as configured, then with PX4's return
# height set too high (RTL_RETURN_ALT 45). Each run is planned, flown, read and
# verified by scripts/run_mission.py. Runs go to runs/M02/, which git ignores.
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-.venv/bin/python}
PX4=${PX4_DIR:?set PX4_DIR to your built PX4-Autopilot checkout}
M=runs/M02
[ -d "$M" ] || { mkdir -p runs && cp -R demo/geofence/M02 "$M"; }
for run in R01 R02; do
  config=platform_configs/px4.yaml
  [ "$run" = R02 ] && config=demo/geofence/px4-fault.yaml
  echo "== $run with $config"
  $PY demo/geofence/fly_locked.py --mission "$M" --px4 "$PX4" --config "$config" \
    --run-id "$run" --seed 4
  echo "   exit $?"
done
$PY demo/geofence/show.py "$M/R01/verdict.json" "$M/R02/verdict.json"
