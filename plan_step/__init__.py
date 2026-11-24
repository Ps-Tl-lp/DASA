"""The plan step: a mission (start.xml, goal.xml and their settings) to a .plan file.

    python -m plan_step MISSION_FOLDER [--settings PATH] [--out PATH] [--config PATH]

From Python, plan_mission(start, goal, settings, config) plans states held in memory
(the generator's call) and returns the plan. NoPlan means the drone can't fly the
mission, NotSupported that this version can't plan it, and PlanError that the input
is wrong. A script in scripts/ needs the repo root on sys.path to import plan_step.

The rules come from platform_configs/px4.yaml (`tasks`, `plan_item_defaults`,
`inputs`, `plan_template`, `base_lat_lon`). This version covers the simple mission:
takeoff, a goto with a hold at each waypoint, and return home.
"""

from .geo import metres_to_lat_lon
from .plan import (
    NoPlan,
    NotSupported,
    PlanError,
    build_plan,
    plan_exists,
    plan_mission,
    plan_text,
)

__all__ = [
    "NoPlan",
    "NotSupported",
    "PlanError",
    "build_plan",
    "metres_to_lat_lon",
    "plan_exists",
    "plan_mission",
    "plan_text",
]
