"""python -m plan_step MISSION_FOLDER [--settings PATH] [--out PATH] [--config PATH]"""

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, load_config
from .plan import PlanError, build_plan, plan_text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m plan_step", description=__doc__)
    parser.add_argument(
        "mission", type=Path, help="folder with start.xml, goal.xml and their settings"
    )
    parser.add_argument(
        "--settings",
        type=Path,
        help="the mission settings the states were made from "
        "(default: the one .yaml file in MISSION)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="where to write the .plan (default: MISSION/mission.plan)",
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="platform config"
    )
    args = parser.parse_args(argv)

    try:
        plan = build_plan(
            args.mission, load_config(args.config), settings=args.settings
        )
    except PlanError as error:
        print(f"no plan: {error}", file=sys.stderr)
        return 1
    out = args.out or args.mission / "mission.plan"
    out.write_text(plan_text(plan))
    print(f"wrote {out} ({len(plan['mission']['items'])} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
