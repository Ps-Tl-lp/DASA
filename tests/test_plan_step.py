"""Tests for the plan step (plan_step/).

Expected values come from outside the plan step: the M01 fixture's mission.plan, our
missions/simple.plan, the config itself, and a great-circle distance worked out
independently below.
"""

import json
import math
from pathlib import Path

import pytest
import yaml

from plan_step import (
    NotSupported,
    PlanError,
    build_plan,
    metres_to_lat_lon,
    plan_exists,
    plan_text,
)
from plan_step.__main__ import main
from plan_step.config import load_config
from plan_step.states import waypoint_ids

ROOT = Path(__file__).resolve().parent.parent
M01 = ROOT / "tests" / "fixtures" / "m01"
CONFIG = load_config()
HOME = CONFIG["base_lat_lon"]


# ---- Writing small missions for the tests --------------------------------------------


def _state_xml(env_id, waypoints, landed=True, extra_waypoint_xml="", base=(0, 0, 0)):
    """A state file like the M01 fixture's. waypoints: {id: (x, y, z, visited)}."""
    wps = "".join(
        f'  <waypoint id="{wp}">\n'
        f'    <x type="float" unit="m" value="{x}"/>\n'
        f'    <y type="float" unit="m" value="{y}"/>\n'
        f'    <z type="float" unit="m" value="{z}"/>\n'
        f'    <visited type="bool" value="{str(visited).lower()}"/>\n'
        f"{extra_waypoint_xml}"
        f"  </waypoint>\n"
        for wp, (x, y, z, visited) in waypoints.items()
    )
    return (
        f'<env id="{env_id}" type="px4">\n'
        '  <base id="B1">\n'
        f'    <x type="float" unit="m" value="{base[0]}"/>\n'
        f'    <y type="float" unit="m" value="{base[1]}"/>\n'
        f'    <z type="float" unit="m" value="{base[2]}"/>\n'
        "  </base>\n"
        '  <agent id="A1" base="B1">\n'
        '    <x type="float" unit="m" value="0"/>\n'
        '    <y type="float" unit="m" value="0"/>\n'
        '    <z type="float" unit="m" value="0"/>\n'
        "    <velocity>\n"
        '      <x type="float" unit="m/s" value="0"/>\n'
        '      <y type="float" unit="m/s" value="0"/>\n'
        '      <z type="float" unit="m/s" value="0"/>\n'
        "    </velocity>\n"
        f'    <landed type="bool" value="{str(landed).lower()}"/>\n'
        '    <vehicle_type type="string" value="multicopter"/>\n'
        '    <has_camera type="bool" value="false"/>\n'
        '    <has_grippers type="bool" value="false"/>\n'
        "  </agent>\n"
        f"{wps}"
        "</env>\n"
    )


def _mission(
    folder,
    positions,
    postconditions=(),
    goal_landed=True,
    goal_visited=None,
    goal_extra="",
    start_visited=None,
    base=(0, 0, 0),
):
    """Write mission.yaml, start.xml and goal.xml. positions: {id: (x, y, z)}."""
    folder.mkdir(parents=True, exist_ok=True)
    goal_visited = (
        goal_visited if goal_visited is not None else dict.fromkeys(positions, True)
    )
    start_visited = start_visited or dict.fromkeys(positions, False)
    start = {wp: (*xyz, start_visited[wp]) for wp, xyz in positions.items()}
    goal = {wp: (*xyz, goal_visited[wp]) for wp, xyz in positions.items()}
    (folder / "start.xml").write_text(_state_xml("S1", start, base=base))
    (folder / "goal.xml").write_text(
        _state_xml(
            "Sg", goal, landed=goal_landed, extra_waypoint_xml=goal_extra, base=base
        )
    )
    spec = {
        "mission_id": "T",
        "start": "start.xml",
        "goal": "goal.xml",
        "postconditions": list(postconditions),
    }
    (folder / "mission.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    return folder


def _items(folder):
    return build_plan(folder, CONFIG)["mission"]["items"]


def _great_circle_m(lat1, lon1, lat2, lon2, radius=6371000.0):
    """Haversine distance on PX4's sphere, written independently of plan_step.geo."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


# ---- The M01 fixture and QGroundControl's plan ---------------------------------------


def test_m01_plan_is_the_fixture_file_byte_for_byte():
    assert plan_text(build_plan(M01, CONFIG)) == (M01 / "mission.plan").read_text()


def test_w1_lat_lon_matches_missions_simple_plan():
    simple = json.loads((ROOT / "missions" / "simple.plan").read_text())
    w1 = simple["mission"]["items"][1]["params"]
    assert metres_to_lat_lon(50, 0, HOME["lat"], HOME["lon"]) == (w1[4], w1[5])


def test_home_is_base_lat_lon_and_the_rest_is_the_template():
    plan = build_plan(M01, CONFIG)
    template = json.loads((ROOT / CONFIG["plan_template"]).read_text())
    assert plan["mission"]["plannedHomePosition"] == [
        HOME["lat"],
        HOME["lon"],
        HOME["alt"],
    ]
    for key in template:
        if key != "mission":
            assert plan[key] == template[key]
    for key in template["mission"]:
        if key not in ("items", "plannedHomePosition"):
            assert plan["mission"][key] == template["mission"][key]


# ---- The lat/lon helper --------------------------------------------------------------


# Flat earth on a sphere is a few millimetres off the great-circle distance close to
# home: about 1 mm at 200 m out, and 2.4 mm at 200 m north and 200 m east (283 m out).
# So 5 mm is the allowance here.
@pytest.mark.parametrize(
    "north, east", [(0, 150), (100, 100), (-200, 0), (120, -160), (200, 200)]
)
def test_lat_lon_lands_the_right_distance_from_home(north, east):
    lat, lon = metres_to_lat_lon(north, east, HOME["lat"], HOME["lon"])
    assert _great_circle_m(HOME["lat"], HOME["lon"], lat, lon) == pytest.approx(
        math.hypot(north, east), abs=0.005
    )


def test_east_moves_longitude_only():
    lat, lon = metres_to_lat_lon(0, 100, HOME["lat"], HOME["lon"])
    assert lat == HOME["lat"] and lon > HOME["lon"]


# ---- Choosing and checking tasks -----------------------------------------------------


def test_takeoff_climbs_to_the_first_waypoint_height(tmp_path):
    items = _items(_mission(tmp_path, {"W1": (40, 10, 30)}))
    takeoff = items[0]
    assert (takeoff["command"], takeoff["params"][6], takeoff["Altitude"]) == (
        22,
        30,
        30,
    )


def test_hold_comes_from_hold_at_and_defaults_to_zero(tmp_path):
    held = _items(
        _mission(
            tmp_path / "a",
            {"W1": (40, 0, 20)},
            [{"hold_at": {"waypoint": "W1", "min_s": 7}}],
        )
    )
    unheld = _items(_mission(tmp_path / "b", {"W1": (40, 0, 20)}))
    assert held[1]["params"][0] == 7
    assert unheld[1]["params"][0] == 0


def test_goto_uses_the_at_waypoint_radius_and_items_are_numbered_from_one(tmp_path):
    items = _items(_mission(tmp_path, {"W1": (40, 0, 20)}))
    assert items[1]["params"][1] == CONFIG["tolerances"]["at_waypoint"]["within_m"]
    assert [item["doJumpId"] for item in items] == [1, 2, 3]
    assert [item["command"] for item in items] == [22, 16, 20]


def test_gotos_follow_waypoint_id_order(tmp_path):
    items = _items(_mission(tmp_path, {"W10": (100, 0, 20), "W2": (60, 0, 20)}))
    out = [
        _great_circle_m(HOME["lat"], HOME["lon"], it["params"][4], it["params"][5])
        for it in items[1:3]
    ]
    assert out == [pytest.approx(60, abs=0.005), pytest.approx(100, abs=0.005)]


def test_no_change_gives_no_items(tmp_path):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)}, goal_visited={"W1": False})
    assert _items(folder) == []


def test_a_goal_the_tasks_cant_reach_has_no_plan(tmp_path):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)}, goal_landed=False)
    with pytest.raises(PlanError, match="agent.landed"):
        build_plan(folder, CONFIG)


def test_hold_at_an_unknown_waypoint_has_no_plan(tmp_path):
    folder = _mission(
        tmp_path, {"W1": (40, 0, 20)}, [{"hold_at": {"waypoint": "W9", "min_s": 5}}]
    )
    with pytest.raises(PlanError, match="W9"):
        build_plan(folder, CONFIG)


def test_hold_at_a_waypoint_the_goal_leaves_unvisited_has_no_plan(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20), "W2": (80, 0, 20)},
        [{"hold_at": {"waypoint": "W2", "min_s": 5}}],
        goal_visited={"W1": True, "W2": False},
    )
    with pytest.raises(PlanError, match="isn't visited"):
        build_plan(folder, CONFIG)


def test_a_picture_is_not_supported_yet(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20)},
        goal_extra='    <clicked_pic type="bool" value="true"/>\n',
    )
    with pytest.raises(NotSupported, match="clicked_pic"):
        build_plan(folder, CONFIG)


def test_a_visit_order_is_not_supported_yet(tmp_path):
    folder = _mission(
        tmp_path, {"W1": (40, 0, 20)}, [{"visits_in_order": {"waypoints": ["W1"]}}]
    )
    with pytest.raises(NotSupported, match="visits_in_order"):
        build_plan(folder, CONFIG)


def test_a_geofence_postcondition_doesnt_change_the_plan(tmp_path):
    fenced = _mission(
        tmp_path / "a",
        {"W1": (40, 0, 20)},
        [{"stays_in_geofence": {"max_distance_m": 60, "max_height_m": 35}}],
    )
    plain = _mission(tmp_path / "b", {"W1": (40, 0, 20)})
    assert _items(fenced) == _items(plain)


def test_plan_exists_gives_the_reason(tmp_path):
    assert plan_exists(M01, CONFIG) == (True, "")
    ok, reason = plan_exists(
        _mission(tmp_path, {"W1": (40, 0, 20)}, goal_landed=False), CONFIG
    )
    assert not ok and "agent.landed" in reason


# ---- The command line ----------------------------------------------------------------


def test_command_line_writes_the_plan(tmp_path, capsys):
    out = tmp_path / "m01.plan"
    assert main([str(M01), "--out", str(out)]) == 0
    assert out.read_text() == (M01 / "mission.plan").read_text()


def test_command_line_says_why_there_is_no_plan(tmp_path, capsys):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)}, goal_landed=False)
    assert main([str(folder), "--out", str(tmp_path / "x.plan")]) == 1
    assert "no plan:" in capsys.readouterr().err
    assert not (tmp_path / "x.plan").exists()


# ---- Which waypoint, which height, which goto ----------------------------------------


def test_each_hold_goes_to_the_waypoint_its_hold_at_names(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20), "W2": (80, 0, 20)},
        [{"hold_at": {"waypoint": "W2", "min_s": 7}}],
    )
    assert [item["params"][0] for item in _items(folder)[1:3]] == [0, 7]


def test_takeoff_height_is_the_first_gotos(tmp_path):
    items = _items(_mission(tmp_path, {"W1": (40, 0, 25), "W2": (80, 0, 40)}))
    assert items[0]["params"][6] == 25


def test_a_waypoint_that_doesnt_change_gets_no_goto(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20), "W2": (80, 0, 20)},
        goal_visited={"W1": True, "W2": False},
    )
    assert [item["command"] for item in _items(folder)] == [22, 16, 20]


def test_a_goto_east_of_home_lands_east_at_the_right_distance(tmp_path):
    goto = _items(_mission(tmp_path, {"W1": (0, 100, 20)}))[1]
    lat, lon = goto["params"][4], goto["params"][5]
    assert lat == HOME["lat"] and lon > HOME["lon"]
    assert _great_circle_m(HOME["lat"], HOME["lon"], lat, lon) == pytest.approx(
        100, abs=0.005
    )


def test_hold_at_on_a_mission_that_changes_nothing_has_no_plan(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20)},
        [{"hold_at": {"waypoint": "W1", "min_s": 5}}],
        goal_visited={"W1": False},
    )
    ok, reason = plan_exists(folder, CONFIG)
    assert not ok and "isn't visited" in reason


def test_hold_at_a_waypoint_already_visited_still_flies_there(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20)},
        [{"hold_at": {"waypoint": "W1", "min_s": 5}}],
        start_visited={"W1": True},
    )
    items = _items(folder)
    assert [item["command"] for item in items] == [22, 16, 20]
    assert items[1]["params"][0] == 5


def test_a_goal_with_nothing_to_fly_to_names_the_property(tmp_path):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)}, goal_visited={"W1": False})
    goal = (folder / "goal.xml").read_text()
    has_camera = '<has_camera type="bool" value="false"/>'
    (folder / "goal.xml").write_text(
        goal.replace(has_camera, has_camera.replace("false", "true"))
    )
    ok, reason = plan_exists(folder, CONFIG)
    assert not ok and "agent.has_camera" in reason


def test_a_base_away_from_the_origin_has_no_plan(tmp_path):
    folder = _mission(tmp_path, {"W1": (60, 5, 23)}, base=(10, 5, 3))
    ok, reason = plan_exists(folder, CONFIG)
    assert not ok and "0, 0, 0" in reason


def test_not_supported_is_raised_not_reported_as_impossible(tmp_path):
    folder = _mission(
        tmp_path,
        {"W1": (40, 0, 20)},
        goal_extra='    <clicked_pic type="bool" value="true"/>\n',
    )
    with pytest.raises(NotSupported):
        plan_exists(folder, CONFIG)


# ---- Files written slightly differently ----------------------------------------------


@pytest.mark.parametrize(
    "old, new, named",
    [
        (
            '<visited type="bool" value="false"/>',
            '<visited type="bool" value="maybe"/>',
            "visited",
        ),
        ('<visited type="bool" value="false"/>', '<visited value="false"/>', "visited"),
        (
            '<visited type="bool" value="false"/>',
            '<visited type="bool">false</visited>',
            "visited",
        ),
        (
            '<z type="float" unit="m" value="20"/>',
            '<z type="decimal" unit="m" value="20"/>',
            "z",
        ),
        (
            '<z type="float" unit="m" value="20"/>',
            '<z type="float" unit="m" value=""/>',
            "z",
        ),
    ],
)
def test_a_state_file_we_cant_read_has_no_plan_and_names_the_property(
    tmp_path, old, new, named
):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)})
    start = (folder / "start.xml").read_text()
    assert old in start
    (folder / "start.xml").write_text(start.replace(old, new))
    ok, reason = plan_exists(folder, CONFIG)
    assert not ok and f"W1.{named}" in reason


def test_double_and_one_zero_bools_are_read(tmp_path):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)})
    start = (folder / "start.xml").read_text()
    start = start.replace(
        '<visited type="bool" value="false"/>', '<visited type="bool" value="0"/>'
    )
    start = start.replace(
        '<z type="float" unit="m" value="20"/>',
        '<z type="double" unit="m" value="20"/>',
    )
    (folder / "start.xml").write_text(start)
    assert [item["command"] for item in _items(folder)] == [22, 16, 20]


@pytest.mark.parametrize(
    "postconditions, works",
    [
        (None, True),  # `postconditions:` with nothing under it
        (["disarmed_after_landing"], True),  # a bare name
        ([{"hold_at": {"waypoint": "W1"}}], False),  # no min_s
        ([{"hold_at": {"min_s": 5}}], False),  # no waypoint
    ],
)
def test_postconditions_written_in_other_ways(tmp_path, postconditions, works):
    folder = _mission(tmp_path, {"W1": (40, 0, 20)})
    spec = yaml.safe_load((folder / "mission.yaml").read_text())
    spec["postconditions"] = postconditions
    (folder / "mission.yaml").write_text(yaml.safe_dump(spec))
    assert plan_exists(folder, CONFIG)[0] is works


def test_a_numeric_waypoint_id_matches_its_hold_at(tmp_path):
    folder = _mission(tmp_path, {"1": (40, 0, 20)})
    spec = yaml.safe_load((folder / "mission.yaml").read_text())
    spec["postconditions"] = [{"hold_at": {"waypoint": 1, "min_s": 5}}]
    (folder / "mission.yaml").write_text(yaml.safe_dump(spec))
    assert _items(folder)[1]["params"][0] == 5


def test_waypoints_that_sort_equal_as_numbers_keep_a_fixed_order():
    state = {"waypoint.W1.x": 0, "waypoint.W01.x": 0, "waypoint.W2.x": 0}
    assert waypoint_ids(state) == ["W01", "W1", "W2"]
