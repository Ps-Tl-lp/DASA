"""Turn a mission into a QGroundControl .plan file (the plan step).

What it does, in the order the config's `tasks` section describes:

1. List the tasks in a fixed order: takeoff, a goto for each waypoint that needs one (in
   waypoint id order), return_home. A waypoint a hold_at names always gets a goto. If
   nothing changes and nothing is held, there are no tasks at all.
2. Check the list: walk it from the start state. Each task's `needs` must hold, then its
   `sets` apply. The result must equal the goal state. If not, there is no plan, and the
   error says which task and property failed.
3. Write one .plan item per task from its `plan_item`, filling in the $ values that
   `inputs` describes, and copy everything else from the plan template.

Only what the simple mission needs is here: takeoff, goto with a hold, return_home. A
mission that asks for more (a picture, a visit order) is refused with NotSupported.
"""

import copy
import json
from pathlib import Path

import yaml

from .config import REPO_ROOT, follow, is_config_name, load_config
from .geo import metres_to_lat_lon
from .states import StateError, read_state, waypoint_ids

# The tasks this version can plan.
SUPPORTED_TASKS = ("takeoff", "goto", "return_home")

# Postconditions the plan step understands. hold_at sets a goto's hold time. The plan
# step has nothing to do for the others: the generator and the verifier check them.
PLAN_POSTCONDITIONS = {"hold_at"}
IGNORED_POSTCONDITIONS = {"stays_in_geofence", "disarmed_after_landing"}

# QGroundControl's own key order for an item, as in missions/simple.plan. Keeping it
# makes our files diff cleanly against plans made in QGroundControl.
ITEM_KEY_ORDER = [
    "type",
    "frame",
    "command",
    "autoContinue",
    "doJumpId",
    "params",
    "AMSLAltAboveTerrain",
    "Altitude",
    "AltitudeMode",
]

# Helpers that `inputs` can name.
HELPERS = {"metres_to_lat_lon": metres_to_lat_lon}

# The state prefixes a needs/sets value can start with.
STATE_PREFIXES = ("agent.", "waypoint.", "base.")


class PlanError(Exception):
    """The mission has no plan. The message names the task and property that failed."""


class NotSupported(PlanError):
    """The mission asks for something this version of the plan step doesn't do."""


class Mission:
    """A mission folder: mission.yaml plus the two states it names."""

    def __init__(self, folder):
        folder = Path(folder)
        try:
            with open(folder / "mission.yaml") as f:
                spec = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as error:
            raise PlanError(f"can't read mission.yaml: {error}") from error
        if not isinstance(spec, dict):
            raise PlanError("mission.yaml isn't a mapping of keys to values")
        for key in ("mission_id", "start", "goal"):
            if key not in spec:
                raise PlanError(f"mission.yaml has no {key}")
        for key in ("start", "goal"):
            if not isinstance(spec[key], str) or not spec[key]:
                raise PlanError(f"mission.yaml's {key} must be a file name")
        postconditions = spec.get("postconditions") or []
        if not isinstance(postconditions, list):
            raise PlanError("mission.yaml's postconditions must be a list")
        self.mission_id = spec["mission_id"]
        try:
            self.start = read_state(folder / spec["start"])
            self.goal = read_state(folder / spec["goal"])
        except StateError as error:
            raise PlanError(str(error)) from error
        self.postconditions = [_postcondition(p) for p in postconditions]
        self.waypoints = waypoint_ids(self.start)
        # Positions are metres from the base, so the base is the origin. A base anywhere
        # else would mean subtracting it from every position, sideways and up.
        base = tuple(self.start.get(f"base.{axis}") for axis in "xyz")
        if base != (0, 0, 0):
            raise PlanError(
                "the base must be at 0, 0, 0, because positions are measured from it; "
                f"it is at {base}"
            )

    def holds(self):
        """{waypoint id: hold_at fields} for every hold_at postcondition."""
        holds = {}
        for name, fields in self.postconditions:
            if name == "hold_at":
                if "waypoint" not in fields:
                    raise PlanError("a hold_at has no waypoint")
                holds[fields["waypoint"]] = fields
        return holds


def _postcondition(item):
    """One postconditions entry as (name, fields): `- hold_at: {...}` or `- name`."""
    if isinstance(item, str):
        return item, {}
    if isinstance(item, dict) and len(item) == 1:
        name, fields = next(iter(item.items()))
        if fields is None:
            fields = {}
        if not isinstance(name, str) or not isinstance(fields, dict):
            raise PlanError(f"postcondition {item!r} isn't one `name: {{fields}}` item")
        fields = dict(fields)
        if "waypoint" in fields:
            fields["waypoint"] = str(fields["waypoint"])  # YAML reads `1` as a number
        if name == "hold_at" and "min_s" in fields:
            hold = fields["min_s"]
            if isinstance(hold, bool) or not isinstance(hold, int | float) or hold < 0:
                raise PlanError(
                    f"hold_at's min_s must be a number of seconds, not {hold!r}"
                )
        return name, fields
    raise PlanError(f"postcondition {item!r} isn't one `name: {{fields}}` item")


def build_plan(mission_folder, config=None):
    """The whole .plan file for a mission, as a dict ready for json.dump."""
    config = config or load_config()
    mission = Mission(mission_folder)
    tasks = choose_tasks(config, mission)
    check_tasks(config, mission, tasks)
    items = [_plan_item(config, mission, tasks, i) for i in range(len(tasks))]

    with open(REPO_ROOT / config["plan_template"]) as f:
        plan = json.load(f)
    plan = copy.deepcopy(plan)
    home = config["base_lat_lon"]
    plan["mission"]["plannedHomePosition"] = [home["lat"], home["lon"], home["alt"]]
    plan["mission"]["items"] = items
    return plan


def plan_text(plan):
    """The .plan file's text: two-space JSON, numbers written as QGroundControl does."""
    return json.dumps(_qgc_numbers(plan), indent=2) + "\n"


def plan_exists(mission_folder, config=None):
    """The `plan_exists` helper: (True, "") if there is a plan, else (False, reason).

    NotSupported is raised, not returned: "this version can't plan it yet" is not "the
    drone can't do it", and the generator shouldn't move on to another vehicle type.
    """
    try:
        build_plan(mission_folder, config)
    except NotSupported:
        raise
    except PlanError as error:
        return False, str(error)
    return True, ""


# ---- 1. Choosing the tasks -----------------------------------------------------------


def choose_tasks(config, mission):
    """The task list in the fixed order, as [(task name, waypoint id or None), ...]."""
    for name, _fields in mission.postconditions:
        if name not in PLAN_POSTCONDITIONS | IGNORED_POSTCONDITIONS:
            raise NotSupported(
                f"postcondition {name} is not supported by this plan step"
            )

    changed = [
        prop
        for prop in mission.goal
        if _start_value(mission, prop) != mission.goal[prop]
    ]
    for prop in changed:
        if prop.endswith(".clicked_pic"):
            raise NotSupported(
                f"{prop} changes, but taking pictures is not supported yet"
            )

    holds = mission.holds()
    for wp in holds:
        if wp not in mission.waypoints:
            raise PlanError(
                f"hold_at names waypoint {wp}, which the mission doesn't have"
            )
        if mission.goal.get(f"waypoint.{wp}.visited") is not True:
            raise PlanError(
                f"hold_at names waypoint {wp}, but the goal says it isn't visited"
            )

    gotos = [
        ("goto", wp)
        for wp in mission.waypoints
        if f"waypoint.{wp}.visited" in changed or wp in holds
    ]
    if not gotos:
        if not changed:
            return []  # nothing to do: no items at all, not even a takeoff
        raise PlanError(
            f"the goal changes {', '.join(changed)}, but no waypoint needs a goto, "
            "so there is nothing to fly"
        )
    tasks = [("takeoff", None), *gotos, ("return_home", None)]
    for name, _wp in tasks:
        if name not in config["tasks"]:
            raise PlanError(f"task {name} is not in the config")
    return tasks


def _start_value(mission, prop):
    # A waypoint that doesn't list clicked_pic counts as false.
    if prop.endswith(".clicked_pic"):
        return mission.start.get(prop, False)
    return mission.start.get(prop)


# ---- 2. Checking the tasks -----------------------------------------------------------


def check_tasks(config, mission, tasks):
    """Walk the tasks from the start state; PlanError at the first step that fails."""
    state = dict(mission.start)
    for wp in mission.waypoints:
        state.setdefault(f"waypoint.{wp}.clicked_pic", False)

    for index, (name, wp) in enumerate(tasks):
        task = config["tasks"][name]
        label = f"{name} {wp}" if wp else name
        for prop, wanted in task.get("needs", {}).items():
            key = _scoped(prop, wp)
            want = _value(config, mission, tasks, index, wanted, state)
            if state.get(key) != want:
                raise PlanError(
                    f"{label} needs {key} = {want!r}, but it is {state.get(key)!r}"
                )
        for prop, given in task.get("sets", {}).items():
            state[_scoped(prop, wp)] = _value(
                config, mission, tasks, index, given, state
            )

    last = tasks[-1][0] if tasks else "the start state"
    for prop, want in mission.goal.items():
        have = state.get(prop, False if prop.endswith(".clicked_pic") else None)
        if have != want:
            raise PlanError(
                f"after {last}, {prop} is {have!r}, but the goal wants {want!r}"
            )


def _scoped(prop, wp):
    """`waypoint.visited` in a goto for W1 means `waypoint.W1.visited`."""
    if prop.startswith("waypoint.") and wp:
        return f"waypoint.{wp}." + prop[len("waypoint.") :]
    return prop


# ---- 3. Writing the items ------------------------------------------------------------


def _plan_item(config, mission, tasks, index):
    name, _wp = tasks[index]
    spec = config["tasks"][name]["plan_item"]
    item = {
        "command": spec["command"],
        "frame": spec["frame"],
        "params": [
            _value(config, mission, tasks, index, p, mission.start)
            for p in spec["params"]
        ],
    }
    for key, value in config["plan_item_defaults"].items():
        item[key] = _value(
            config, mission, tasks, index, value, mission.start, item=item
        )
    ordered = {key: item[key] for key in ITEM_KEY_ORDER if key in item}
    ordered.update({key: value for key, value in item.items() if key not in ordered})
    return ordered


# ---- Values --------------------------------------------------------------------------


def _value(config, mission, tasks, index, value, state, item=None):
    """What a config value means for task number `index` (see the config's header)."""
    _name, wp = tasks[index]
    if isinstance(value, str) and value.startswith("$"):
        return _input(config, mission, tasks, index, value, item)
    if isinstance(value, str) and value.startswith(STATE_PREFIXES):
        key = _scoped(value, wp)
        if key not in state:
            raise PlanError(
                f"{value} has no value for task {_name} {wp or ''}".rstrip()
            )
        return state[key]
    if is_config_name(config, value):
        return follow(config, value)
    return value  # a plain value, used as written


def _input(config, mission, tasks, index, dollar_name, item):
    """A $ value, filled in the way the config's `inputs` row for it says."""
    row = config["inputs"].get(dollar_name)
    if row is None:
        raise PlanError(f"{dollar_name} has no row in the config's inputs")
    _name, wp = tasks[index]
    source = row["from"]

    if source == "first_goto":
        first = next((w for n, w in tasks if n == "goto"), None)
        if first is None:
            raise PlanError(
                f"{dollar_name} needs a goto in the plan, and there is none"
            )
        return mission.start[_scoped(row["value"], first)]

    if source == "postcondition":
        for name, fields in mission.postconditions:
            if name == row["name"] and fields.get("waypoint") == wp:
                if row["field"] not in fields:
                    raise PlanError(f"{name} for {wp} has no {row['field']}")
                return fields[row["field"]]
        return row["default"]

    if source == "waypoint":
        helper = HELPERS[row["helper"]]
        home = config["base_lat_lon"]
        north = mission.start[f"waypoint.{wp}.x"]  # metres from the base, the origin
        east = mission.start[f"waypoint.{wp}.y"]
        results = dict(
            zip(
                config["helpers"][row["helper"]]["returns"],
                helper(north, east, home["lat"], home["lon"]),
                strict=True,
            )
        )
        return results[row["output"]]

    if source == "item":
        if row["value"] == "position_in_plan":
            return index + 1  # QGroundControl numbers items from 1
        if row["value"].startswith("param_"):
            return item["params"][int(row["value"].split("_")[1]) - 1]

    raise PlanError(f"{dollar_name}: don't know how to fill a value from {source!r}")


def _qgc_numbers(value):
    """Write 20.0 as 20, as QGroundControl does, so our files match plans made there."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_qgc_numbers(v) for v in value]
    if isinstance(value, dict):
        return {k: _qgc_numbers(v) for k, v in value.items()}
    return value
