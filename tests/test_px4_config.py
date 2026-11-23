"""Check that platform_configs/px4.yaml hangs together.

These tests don't judge whether the values are right. They catch a config that
no longer loads, breaks its own rules for how values are written (the list at
the top of the file), or stops matching the simple mission plan we already fly.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "platform_configs" / "px4.yaml").read_text())
PLAN = json.loads((ROOT / CONFIG["plan_template"]).read_text())["mission"]
PLAN_ITEMS = PLAN["items"]
ZONE = "tolerances.at_waypoint"


def lookup(dotted_name):
    """Follow a name like tolerances.at_waypoint.within_m into the config."""
    value = CONFIG
    for key in dotted_name.split("."):
        value = value[key]
    return value


def every_value(node=CONFIG):
    """Every value in the config, however deeply it is nested. Keys are left out."""
    if isinstance(node, dict):
        for child in node.values():
            yield from every_value(child)
    elif isinstance(node, list):
        for child in node:
            yield from every_value(child)
    else:
        yield node


def every_value_under(key, node=CONFIG):
    """Every value stored under `key`, anywhere in the config."""
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for child in node.values():
            yield from every_value_under(key, child)
    elif isinstance(node, list):
        for child in node:
            yield from every_value_under(key, child)


def every_check():
    """Each check in the config, as (name, check)."""
    preconditions = CONFIG["preconditions"]
    for section in (
        preconditions["mission"],
        preconditions["tasks"],
        CONFIG["derived"],
        CONFIG["postconditions"],
    ):
        yield from section.items()


def test_config_has_the_sections_each_step_reads():
    sections = {
        "vehicle_types",
        "px4_setup",
        "preconditions",
        "tasks",
        "plan_item_defaults",
        "plan_template",
        "base_lat_lon",
        "inputs",
        "readings",
        "not_in_log",
        "derived",
        "goal_check",
        "postconditions",
        "helpers",
        "tolerances",
        "log_only_readings",
        "time_zero_topics",
        "cross_check",
        "sim",
    }
    assert sections <= set(CONFIG)


def test_every_dotted_name_points_somewhere():
    # tolerances.x.y has to exist in this file. agent.x, waypoint.z and base.x
    # are state properties, so they only need the right first word.
    dotted_name = re.compile(r"[A-Za-z_]\w*(\.\w+)+")
    names = [
        v for v in every_value() if isinstance(v, str) and dotted_name.fullmatch(v)
    ]
    assert names
    for name in names:
        first_word = name.split(".")[0]
        if first_word in CONFIG:
            lookup(name)  # a missing key raises KeyError
        else:
            assert first_word in {"agent", "waypoint", "base"}, name


def test_allowed_vehicle_types_are_the_ones_defined():
    allowed = CONFIG["preconditions"]["global"]["allowed_values"]
    assert set(allowed["agent.vehicle_type"]) == set(CONFIG["vehicle_types"])


def test_every_dollar_value_has_one_row_in_inputs():
    used = {v for v in every_value() if isinstance(v, str) and v.startswith("$")}
    assert used == set(CONFIG["inputs"])
    # `from` is one of the kinds listed above `inputs` in the config.
    kinds = {"postcondition", "first_goto", "waypoint", "item"}
    for name, row in CONFIG["inputs"].items():
        assert row["from"] in kinds, name


def test_every_helper_is_listed_in_helpers():
    assert set(every_value_under("helper")) == set(CONFIG["helpers"])


def test_every_check_has_a_rule_and_reads_real_readings():
    for name, check in every_check():
        assert isinstance(check["rule"], str) and check["rule"], name
    # Checks on the flight say which readings they use. The ones before it have none.
    after_the_flight = [
        *CONFIG["derived"].items(),
        *CONFIG["postconditions"].items(),
        *(("goal_check", comparison) for comparison in CONFIG["goal_check"]["within"]),
    ]
    for name, check in after_the_flight:
        assert check["reads"], name
        for reading in check["reads"]:
            assert reading in CONFIG["readings"], f"{name} reads {reading}"


def test_hold_counts_in_mission_mode_with_a_named_allowance():
    hold = CONFIG["postconditions"]["hold_at"]
    assert "nav_state" in hold["reads"]
    assert hold["in_nav_state"] == 3  # NAVIGATION_STATE_AUTO_MISSION
    assert hold["short_by_at_most"] == "tolerances.hold_short_by_s"
    assert 0 < lookup(hold["short_by_at_most"]) < 1


def test_every_mission_flags_are_booleans():
    for name, check in CONFIG["postconditions"].items():
        assert isinstance(check.get("every_mission", False), bool), name
    assert CONFIG["postconditions"]["disarmed_after_landing"]["every_mission"] is True


def test_every_reading_names_its_source():
    for section in ("readings", "log_only_readings"):
        for name, row in CONFIG[section].items():
            assert row["source"] in {"gz_pose", "log"}, (section, name)
            if row["source"] == "log":
                assert row["topic"] and row["field"], (section, name)
            else:
                ways = {"field", "rate_of", "on_ground_m"} & set(row)
                assert len(ways) == 1, (section, name)
    assert set(CONFIG["log_only_readings"]) == set(CONFIG["readings"])
    assert {row["source"] for row in CONFIG["log_only_readings"].values()} == {"log"}


def test_rate_of_names_a_reading():
    for section in ("readings", "log_only_readings"):
        for name, row in CONFIG[section].items():
            if "rate_of" in row:
                assert row["rate_of"] in CONFIG[section], (section, name)


def test_the_disarm_check_reads_the_arming_state():
    disarm = CONFIG["postconditions"]["disarmed_after_landing"]
    assert {"arming_state", "disarm_reason", "agent.landed"} <= set(disarm["reads"])
    assert disarm["disarmed_state"] == 1  # ARMING_STATE_DISARMED


def test_the_log_is_checked_against_the_recording():
    cross = CONFIG["cross_check"]
    assert {"log", "same_time_within_s", "max_difference_m", "rule"} <= set(cross)
    assert lookup(CONFIG["cross_check"]["max_difference_m"]) > 0
    assert lookup(CONFIG["cross_check"]["same_time_within_s"]) > 0
    log = CONFIG["cross_check"]["log"]
    assert log["topic"] in CONFIG["time_zero_topics"]
    # the same topic and fields the log-only position readings use
    rows = CONFIG["log_only_readings"]
    assert all(rows[f"agent.{a}"]["topic"] == log["topic"] for a in "xyz")
    assert [rows[f"agent.{a}"]["field"] for a in "xyz"] == [
        log["north"],
        log["east"],
        log["down"],
    ]
    assert CONFIG["sim"]["pose_topic"].startswith(f"/world/{CONFIG['sim']['world']}/")


def test_every_task_has_needs_and_sets_on_state_properties():
    for name, task in CONFIG["tasks"].items():
        assert "takes" not in task, name  # inputs says where every $ value comes from
        for part in ("needs", "sets"):
            assert task[part], (name, part)
            for prop in task[part]:
                assert prop.split(".")[0] in {"agent", "waypoint", "base"}, (name, prop)


def test_a_log_gap_and_the_simulator_setup_are_named():
    assert CONFIG["postconditions"]["hold_at"]["max_gap"] == "tolerances.log_gap_max_s"
    assert 0 < lookup("tolerances.log_gap_max_s") < 1
    sim = CONFIG["sim"]
    assert isinstance(sim["speed_factor"], (int, float)) and sim["speed_factor"] > 0
    assert isinstance(sim["px4_build"], str) and sim["px4_build"]
    assert sim["simulator"] and isinstance(sim["headless"], bool)


def test_px4_gets_the_same_waypoint_zone_as_the_checks():
    # Sideways goes into each goto item, height into a PX4 setting.
    assert CONFIG["tasks"]["goto"]["plan_item"]["params"][1] == f"{ZONE}.within_m"
    assert CONFIG["px4_setup"]["NAV_MC_ALT_RAD"] == f"{ZONE}.height_within_m"
    assert set(every_value_under("zone")) == {ZONE}


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
    tasks = ["takeoff", "goto", "return_home"]
    for item, task in zip(PLAN_ITEMS, tasks, strict=True):
        plan_item = CONFIG["tasks"][task]["plan_item"]
        assert item["command"] == plan_item["command"], task
        assert item["frame"] == plan_item["frame"], task
        assert len(item["params"]) == len(plan_item["params"]), task


def test_base_is_where_the_simple_plan_starts():
    home_lat, home_lon, home_alt = PLAN["plannedHomePosition"]
    assert CONFIG["base_lat_lon"] == {"lat": home_lat, "lon": home_lon, "alt": home_alt}


def test_each_helper_output_is_one_the_helper_returns():
    for name, spec in CONFIG["inputs"].items():
        if "output" in spec:
            returns = CONFIG["helpers"][spec["helper"]]["returns"]
            assert spec["output"] in returns, name


def test_plan_item_defaults_match_the_simple_plan():
    defaults = CONFIG["plan_item_defaults"]
    for position, item in enumerate(PLAN_ITEMS, start=1):
        # A task's plan_item plus the defaults is everything an item has.
        assert set(item) == {"command", "frame", "params"} | set(defaults)
        for key, value in defaults.items():
            if not str(value).startswith("$"):
                assert item[key] == value, key
        # What the plan we copy does for the two $ values.
        assert item["doJumpId"] == position
        assert item["Altitude"] == item["params"][6]
