"""Check the plans in missions/ against the written mission definitions.

Expected values come from the definitions in missions/README.md and from the
simulator's default launch point, not from the plan files. Waypoint offsets
are measured from each plan's own home, which one test pins to that launch
point. A failure means a plan no longer matches its definition.
"""

import json
import math
from itertools import pairwise
from pathlib import Path

import pytest

MISSIONS_DIR = Path(__file__).resolve().parent.parent / "missions"

# MAVLink numbers: https://mavlink.io/en/messages/common.html
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_TAKEOFF = 22
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3  # altitude in metres above home

EARTH_RADIUS_M = 6_371_000.0  # PX4's value, src/lib/geo/geo.h at fca3df865a
TOLERANCE_M = 0.5

# Where the simulated drone starts: quick-setup's default PX4_HOME_LAT and
# PX4_HOME_LON (dasa-capstone/quick-setup, docs/HOW-IT-WORKS.md, docs/REFERENCE.md).
LAUNCH_LAT_LON = (47.397971057728974, 8.546163739800146)

MISSION_ALTITUDE_M = {"simple": 20, "medium": 20, "survey": 30}
WAYPOINT_COUNT = {"simple": 1, "medium": 4, "survey": 12}

# (north, east) in metres from home, in flight order.
EXPECTED_WAYPOINTS = {
    "simple": [(50, 0)],
    "medium": [(50, 0), (50, 50), (0, 50), (0, 0)],
}
EXPECTED_HOLDS_S = {"simple": [5], "medium": [0, 0, 0, 0]}


def load_mission(name):
    with open(MISSIONS_DIR / f"{name}.plan", encoding="utf-8") as f:
        return json.load(f)["mission"]


def waypoints(mission):
    return [i for i in mission["items"] if i["command"] == MAV_CMD_NAV_WAYPOINT]


def north_east_m(lat_lon, origin):
    # Equirectangular approximation. At the 100 m scale of these missions it
    # differs from PX4's own projection by a few millimetres.
    (lat, lon), (origin_lat, origin_lon) = lat_lon, origin
    m_per_deg_north = math.radians(1) * EARTH_RADIUS_M
    m_per_deg_east = m_per_deg_north * math.cos(math.radians(origin_lat))
    return (lat - origin_lat) * m_per_deg_north, (lon - origin_lon) * m_per_deg_east


def waypoint_offsets(name):
    mission = load_mission(name)
    home = mission["plannedHomePosition"][:2]
    return [north_east_m(item["params"][4:6], home) for item in waypoints(mission)]


def near(expected):
    return pytest.approx(expected, abs=TOLERANCE_M)


def test_missions_dir_holds_exactly_the_defined_missions():
    plans = {path.stem for path in MISSIONS_DIR.glob("*.plan")}
    assert plans == set(MISSION_ALTITUDE_M)


@pytest.mark.parametrize("name", MISSION_ALTITUDE_M)
def test_mission_is_takeoff_then_waypoints_then_return_to_launch(name):
    commands = [item["command"] for item in load_mission(name)["items"]]
    waypoint_commands = [MAV_CMD_NAV_WAYPOINT] * WAYPOINT_COUNT[name]
    expected = [MAV_CMD_NAV_TAKEOFF, *waypoint_commands, MAV_CMD_NAV_RETURN_TO_LAUNCH]
    assert commands == expected


@pytest.mark.parametrize("name", MISSION_ALTITUDE_M)
def test_planned_home_is_the_simulator_launch_point(name):
    home = load_mission(name)["plannedHomePosition"][:2]
    off_by = math.hypot(*north_east_m(home, LAUNCH_LAT_LON))
    assert off_by <= TOLERANCE_M, f"home is {off_by:.1f} m from the launch point"


@pytest.mark.parametrize("name", MISSION_ALTITUDE_M)
def test_mission_starts_with_takeoff_to_mission_altitude(name):
    first = load_mission(name)["items"][0]
    assert first["command"] == MAV_CMD_NAV_TAKEOFF
    assert first["frame"] == MAV_FRAME_GLOBAL_RELATIVE_ALT
    assert first["params"][6] == near(MISSION_ALTITUDE_M[name])


@pytest.mark.parametrize("name", MISSION_ALTITUDE_M)
def test_every_waypoint_is_at_mission_altitude_above_home(name):
    for item in waypoints(load_mission(name)):
        assert item["frame"] == MAV_FRAME_GLOBAL_RELATIVE_ALT
        assert item["params"][6] == near(MISSION_ALTITUDE_M[name])


@pytest.mark.parametrize("name", EXPECTED_WAYPOINTS)
def test_waypoints_are_at_expected_offsets_in_order(name):
    actual = waypoint_offsets(name)
    expected = EXPECTED_WAYPOINTS[name]
    assert len(actual) == len(expected)
    for number, (got, want) in enumerate(zip(actual, expected, strict=True), start=1):
        off_by = math.dist(got, want)
        assert off_by <= TOLERANCE_M, f"waypoint {number} is {off_by:.1f} m from {want}"


@pytest.mark.parametrize("name", EXPECTED_HOLDS_S)
def test_waypoint_hold_times_match_definition(name):
    # param1 of NAV_WAYPOINT is the hold time in seconds.
    holds = [item["params"][0] for item in waypoints(load_mission(name))]
    assert holds == EXPECTED_HOLDS_S[name]


@pytest.mark.parametrize("name", MISSION_ALTITUDE_M)
def test_every_item_auto_continues(name):
    # Without autoContinue, PX4 stops at the item instead of advancing to
    # the next one, so the mission never reaches RTL on its own.
    for item in load_mission(name)["items"]:
        assert item["autoContinue"] is True


def survey_transects():
    # Endpoints 1-2 are the first transect, 3-4 the second, and so on.
    points = waypoint_offsets("survey")
    return list(zip(points[0::2], points[1::2], strict=True))


def test_survey_transects_run_100_m_north_south():
    for start, end in survey_transects():
        assert end[1] == near(start[1])  # same east offset at both ends
        assert abs(end[0] - start[0]) == near(100)


def test_survey_transects_are_20_m_apart_and_alternate_direction():
    for (a_start, a_end), (b_start, b_end) in pairwise(survey_transects()):
        assert abs(b_start[1] - a_start[1]) == near(20)
        # North changes of opposite sign mean opposite directions.
        assert (a_end[0] - a_start[0]) * (b_end[0] - b_start[0]) < 0


def test_survey_grid_spans_20_to_120_m_north_and_east():
    points = waypoint_offsets("survey")
    for axis in (0, 1):
        values = [point[axis] for point in points]
        assert min(values) == near(20)
        assert max(values) == near(120)
