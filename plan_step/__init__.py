"""The plan step: a mission (start.xml, goal.xml and their settings) to a .plan file.

    python -m plan_step MISSION_FOLDER [--settings PATH] [--out PATH] [--config PATH]

The rules come from platform_configs/px4.yaml (`tasks`, `plan_item_defaults`,
`inputs`, `plan_template`, `base_lat_lon`). This version covers the simple mission:
takeoff, a goto with a hold at each waypoint, and return home.
"""

from .geo import metres_to_lat_lon
from .plan import NotSupported, PlanError, build_plan, plan_exists, plan_text

__all__ = [
    "NotSupported",
    "PlanError",
    "build_plan",
    "metres_to_lat_lon",
    "plan_exists",
    "plan_text",
]
