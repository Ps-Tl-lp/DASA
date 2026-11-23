"""Check that platform_configs/px4.yaml hangs together.

These tests don't judge whether the values are right. They catch a config that
no longer loads, points at a key that isn't there, or stops matching the simple
mission plan we already fly.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_TEXT = (ROOT / "platform_configs" / "px4.yaml").read_text()
CONFIG = yaml.safe_load(CONFIG_TEXT)


def lookup(dotted_name):
    """Follow a name like tolerances.at_waypoint.within_m into the config."""
    value = CONFIG
    for key in dotted_name.split("."):
        value = value[key]
    return value


def test_config_has_the_sections_each_step_reads():
    sections = {
        "vehicle_types",
        "px4_setup",
        "preconditions",
        "tasks",
        "plan_item_defaults",
        "base_lat_lon",
        "readings",
        "not_in_log",
        "derived",
        "goal_check",
        "postconditions",
        "tolerances",
    }
    assert sections <= set(CONFIG)


def test_every_named_tolerance_and_px4_setting_exists():
    # Anywhere the file says tolerances.x.y or px4_setup.X, that key has to exist.
    names = re.findall(r"\b(?:tolerances|px4_setup)\.[\w.]+", CONFIG_TEXT)
    assert names
    for name in names:
        lookup(name.rstrip("."))  # a missing key raises KeyError


def test_checks_only_read_readings_that_exist():
    checks = {**CONFIG["derived"], **CONFIG["postconditions"]}
    for check_name, check in checks.items():
        for reading in check["reads"]:
            assert reading in CONFIG["readings"], f"{check_name} reads {reading}"


def test_height_zone_matches_the_px4_setting():
    zone_height = CONFIG["tolerances"]["at_waypoint"]["height_within_m"]
    assert CONFIG["px4_setup"]["NAV_MC_ALT_RAD"] == zone_height


def test_flight_area_has_room_for_a_geofence():
    # A geofence has to clear PX4's return climb, with the clearance on top.
    lowest_fence = (
        CONFIG["px4_setup"]["RTL_RETURN_ALT"]
        + CONFIG["tolerances"]["geofence_clearance_m"]
    )
    flight_area = CONFIG["preconditions"]["global"]["flight_area"]
    assert flight_area["max_height_m"] >= lowest_fence


def test_tasks_use_the_simple_plans_commands_and_frames():
    # Param values aren't compared: goto's radius differs on purpose
    # (0 in the plan, 2 here).
    plan = json.loads((ROOT / "missions" / "simple.plan").read_text())
    home_lat, home_lon, _ = plan["mission"]["plannedHomePosition"]
    assert CONFIG["base_lat_lon"] == {"lat": home_lat, "lon": home_lon}
    tasks = ["takeoff", "goto", "return_home"]
    for item, task in zip(plan["mission"]["items"], tasks, strict=True):
        plan_item = CONFIG["tasks"][task]["plan_item"]
        assert item["command"] == plan_item["command"], task
        assert item["frame"] == plan_item["frame"], task
        assert len(item["params"]) == len(plan_item["params"]), task
