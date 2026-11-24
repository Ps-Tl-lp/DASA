"""Print a run's verdict, one line per check (demo helper)."""

import json
import sys

for path in sys.argv[1:]:
    verdict = json.load(open(path))
    print(f"{verdict['run_id']}: {verdict['verdict']}")
    for check in verdict["checks"]:
        where = f" {check['waypoint']}" if check.get("waypoint") else ""
        print(f"  {check['verdict']:<12} {check['check']}{where}: {check['reason']}")
