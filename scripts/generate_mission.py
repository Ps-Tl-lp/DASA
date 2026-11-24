import argparse
import copy
import math
import os
import random
import secrets
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

AXES = ("x", "y", "z")

# Positions are metres from the base, so the base is always here.
BASE_POSITION = {"x": 0, "y": 0, "z": 0}

# The state properties the M01 fixture README lists for each part of a state.
# Anything else in the template (no_fly_zone, geofence, dwell_time, visited_at,
# in_range, ...) is left out of the output. vehicle_type goes where the template
# puts it: on the <agent> tag (the team template) or as a child (the M01 fixture).
PROPERTIES = {
    "base": AXES,
    "agent": AXES
    + ("velocity", "landed", "vehicle_type", "has_camera", "has_grippers"),
    "waypoint": AXES + ("visited",),
}
EQUIPMENT = ("has_camera", "has_grippers")

# The only allowed_values the generator reads. Horizontal limits come from the
# flight area and the geofence, not from per-axis ranges.
ALLOWED_VALUE_KEYS = ("agent.vehicle_type", "waypoint.z")

# The only goal the generator can produce so far.
SUPPORTED_GOAL = {"waypoint.visited": True, "agent_ends": "base_landed"}

MAX_DRAWS = 1000  # tries per waypoint before the settings are reported as not fitting

# The id each part gets when the template leaves it blank.
DEFAULT_IDS = {"start": "S1", "goal": "Sg", "agent": "A1", "base": "B1"}


class GeneratorError(Exception):
    """A config, settings file, template or output path the generator cannot use."""

    def __init__(self, source, problems):
        self.problems = list(problems)
        lines = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{source}:\n{lines}")


def _load_yaml(path):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise GeneratorError(path, [f"not valid YAML: {e}"]) from None


def _number(mapping, key, name, problems, positive=False):
    """Return mapping[key] as a float, or report why it can't be used."""
    if not isinstance(mapping, dict) or key not in mapping:
        problems.append(f"{name} is missing")
        return None
    value = mapping[key]
    # YAML reads true/false as bools, and bool is a subclass of int.
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        shown = "blank" if value is None else repr(value)
        problems.append(f"{name} is {shown}, not a number")
        return None
    if value < 0 or (positive and value == 0):
        limit = "more than 0" if positive else "at least 0"
        problems.append(f"{name} is {value!r}, but must be {limit}")
        return None
    return float(value)


def _section(mapping, dotted):
    """Follow a dotted name such as preconditions.global through mapping."""
    for part in dotted.split("."):
        if not isinstance(mapping, dict) or part not in mapping:
            return None
        mapping = mapping[part]
    return mapping


def _resolve(config, value, name, problems):
    """Use the value a name like tolerances.at_waypoint points to."""
    if not isinstance(value, str):
        return value
    found = _section(config, value)
    if found is None:
        problems.append(f"{name} names {value}, which the config doesn't have")
    return found


# ---- Platform config ---------------------------------------------------------


def load_config(config_path):
    """Return the limits the generator draws inside, from the platform config."""
    config = _load_yaml(config_path)
    problems = []

    allowed = _section(config, "preconditions.global.allowed_values")
    if not isinstance(allowed, dict):
        raise GeneratorError(
            config_path,
            ["preconditions.global.allowed_values is missing or not a mapping"],
        )
    known = ", ".join(ALLOWED_VALUE_KEYS)
    for key in allowed:
        if key not in ALLOWED_VALUE_KEYS:
            problems.append(
                f"preconditions.global.allowed_values.{key} is not a key the "
                f"generator reads (expected only {known})"
            )

    vehicle = _pick_vehicle(config, allowed.get("agent.vehicle_type"), problems)

    z_name = "preconditions.global.allowed_values.waypoint.z"
    z_range = allowed.get("waypoint.z")
    z_min = _number(z_range, "min", f"{z_name}.min", problems)
    z_max = None
    if isinstance(z_range, dict) and "max" in z_range:
        z_max = _number(z_range, "max", f"{z_name}.max", problems)

    area_name = "preconditions.global.flight_area"
    area = _section(config, area_name)
    flight_area = (
        _number(area, "max_distance_m", f"{area_name}.max_distance_m", problems, True),
        _number(area, "max_height_m", f"{area_name}.max_height_m", problems, True),
    )

    spacing_name = "preconditions.mission.waypoint_spacing.zone"
    spacing = _section(config, "preconditions.mission.waypoint_spacing")
    zone_ref = spacing.get("zone") if isinstance(spacing, dict) else None
    zone = _resolve(config, zone_ref, spacing_name, problems)
    zone_name = zone_ref if isinstance(zone_ref, str) else spacing_name
    zone_sizes = (
        _number(zone, "within_m", f"{zone_name}.within_m", problems),
        _number(zone, "height_within_m", f"{zone_name}.height_within_m", problems),
    )

    fence_name = "preconditions.mission.stays_in_geofence"
    fence = _section(config, fence_name)
    fence_limits = {}
    for key in ("return_height_m", "clearance_m"):
        ref = fence.get(key) if isinstance(fence, dict) else None
        name = ref if isinstance(ref, str) else f"{fence_name}.{key}"
        value = _resolve(config, ref, f"{fence_name}.{key}", problems)
        fence_limits[key] = _number({key: value}, key, name, problems)

    if z_min is not None and z_max is not None and z_min > z_max:
        problems.append(f"{z_name}: min {z_min!r} is greater than max {z_max!r}")
    if problems:
        raise GeneratorError(config_path, problems)
    return {
        "vehicle": vehicle,
        "z_min": z_min,
        "z_max": z_max,
        "flight_area": flight_area,
        "zone": zone_sizes,
        "return_height": fence_limits["return_height_m"],
        "clearance": fence_limits["clearance_m"],
    }


def _pick_vehicle(config, names, problems):
    """Return (name, flags) for the least-equipped allowed vehicle type.

    Fewest has_* true wins, and a tie goes to the type listed first.
    """
    name = "preconditions.global.allowed_values.agent.vehicle_type"
    if not isinstance(names, list) or not names:
        problems.append(f"{name} should be a list of vehicle types, got {names!r}")
        return None
    types = config.get("vehicle_types") if isinstance(config, dict) else None
    candidates = []
    for vehicle in names:
        entry = types.get(vehicle) if isinstance(types, dict) else None
        if not isinstance(entry, dict):
            problems.append(
                f"{name} lists {vehicle!r}, which vehicle_types doesn't have"
            )
            continue
        flags = {}
        for flag in EQUIPMENT:
            if not isinstance(entry.get(flag), bool):
                problems.append(
                    f"vehicle_types.{vehicle}.{flag} should be true or false"
                )
            flags[flag] = entry.get(flag) is True
        candidates.append((vehicle, flags))
    if not candidates:
        return None
    # PLACEHOLDER: preconditions.tasks (plan_exists) isn't run, so the next type
    # is never tried. Every supported mission flies with the least-equipped type.
    # min() keeps the first of equal counts, so a tie goes to the type listed first.
    return min(candidates, key=lambda candidate: sum(candidate[1].values()))


# ---- Mission settings --------------------------------------------------------


def load_settings(settings_path, config):
    """Return the mission's id, waypoint count, postconditions and geofence."""
    raw = _load_yaml(settings_path)
    if not isinstance(raw, dict):
        raise GeneratorError(settings_path, ["the settings are not a mapping"])
    problems = []
    for key in raw:
        if key not in ("mission_id", "waypoints", "goal", "postconditions"):
            problems.append(f"{key} is not a setting the generator reads")

    mission_id = raw.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id.strip():
        problems.append(f"mission_id should be a name such as M01, got {mission_id!r}")

    count = raw.get("waypoints")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        problems.append(
            f"waypoints should be a whole number of at least 1, got {count!r}"
        )
        count = None

    if raw.get("goal") != SUPPORTED_GOAL:
        problems.append(
            "goal should be {waypoint.visited: true, agent_ends: base_landed}, "
            f"the only goal the generator supports, got {raw.get('goal')!r}"
        )

    postconditions, geofence = [], None
    requested = raw.get("postconditions") or {}
    if not isinstance(requested, dict):
        problems.append(f"postconditions should be a mapping, got {requested!r}")
        requested = {}
    for key, spec in requested.items():
        if key == "hold_at_each_waypoint":
            name = "postconditions.hold_at_each_waypoint"
            _only_keys(spec, ("min_s",), name, problems)
            if _number(spec, "min_s", f"{name}.min_s", problems) is not None:
                for number in range(1, (count or 0) + 1):
                    hold = {"waypoint": f"W{number}", "min_s": spec["min_s"]}
                    postconditions.append({"hold_at": hold})
        elif key == "visits_in_order":
            order = _visit_order(spec, count, problems)
            if order is not None:
                postconditions.append({"visits_in_order": {"waypoints": order}})
        elif key == "stays_in_geofence":
            geofence = _geofence(spec, config, problems)
            if geofence is not None:
                postconditions.append({"stays_in_geofence": dict(spec)})
        else:
            problems.append(f"postconditions.{key} is not one the generator supports")

    if problems:
        raise GeneratorError(settings_path, problems)
    return {
        "mission_id": mission_id,
        "waypoints": count,
        "postconditions": postconditions,
        "geofence": geofence,
        "raw": raw,
    }


def _visit_order(spec, count, problems):
    """Return the requested waypoint ids, in their requested order, or None.

    Each id must be one the mission's waypoints get (W1 to Wn), listed once.
    """
    name = "postconditions.visits_in_order"
    _only_keys(spec, ("waypoints",), name, problems)
    order = spec.get("waypoints") if isinstance(spec, dict) else None
    if not isinstance(order, list) or not order:
        problems.append(
            f"{name}.waypoints should be a list of waypoint ids, got {order!r}"
        )
        return None
    if count is None:
        return None  # the waypoint count is already reported
    ids = [f"W{number}" for number in range(1, count + 1)]
    before = len(problems)
    seen = set()
    for waypoint in order:
        if waypoint not in ids:
            problems.append(
                f"{name}.waypoints lists {waypoint!r}, but the mission's waypoints "
                f"are {', '.join(ids)}"
            )
            continue  # not an id, and possibly not even a string
        if waypoint in seen:
            problems.append(f"{name}.waypoints lists {waypoint} more than once")
        seen.add(waypoint)
    return list(order) if len(problems) == before else None


def _only_keys(spec, keys, name, problems):
    if isinstance(spec, dict):
        for key in spec:
            if key not in keys:
                problems.append(f"{name}.{key} is not a field it takes")


def _geofence(spec, config, problems):
    """Return (max_distance_m, max_height_m) for a requested geofence, or None."""
    name = "postconditions.stays_in_geofence"
    _only_keys(spec, ("max_distance_m", "max_height_m"), name, problems)
    distance = _number(spec, "max_distance_m", f"{name}.max_distance_m", problems, True)
    height = _number(spec, "max_height_m", f"{name}.max_height_m", problems, True)
    if distance is None or height is None:
        return None
    # The checks that need no waypoints, so a geofence that can't work is
    # reported before anything is drawn.
    found = geofence_problems([], (distance, height), config)
    problems += found
    return None if found else (distance, height)


# ---- Mission preconditions ---------------------------------------------------
# Each takes waypoints as [(id, {"x": ..., "y": ..., "z": ...}), ...] and
# returns the problems found, empty when the precondition holds.


def spacing_problems(waypoints, zone):
    """preconditions.mission.waypoint_spacing (the config's zones_apart).

    Every waypoint is more than twice within_m sideways from the base. Two
    waypoints are apart when they are more than twice within_m apart
    sideways, or more than twice height_within_m apart in height.
    """
    within, height_within = zone
    problems = []
    for waypoint_id, point in waypoints:
        sideways = math.hypot(point["x"], point["y"])
        if sideways <= 2 * within:
            problems.append(
                f"{waypoint_id} is {sideways!r} m sideways from the base, but must "
                f"be more than {2 * within!r} m"
            )
    for index, (a_id, a) in enumerate(waypoints):
        for b_id, b in waypoints[index + 1 :]:
            sideways = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            height = abs(a["z"] - b["z"])
            if sideways <= 2 * within and height <= 2 * height_within:
                problems.append(
                    f"{a_id} and {b_id} are {sideways!r} m apart sideways and "
                    f"{height!r} m in height, but must be more than "
                    f"{2 * within!r} m sideways or {2 * height_within!r} m in height"
                )
    return problems


def geofence_problems(waypoints, geofence, config):
    """preconditions.mission.stays_in_geofence, for a mission with a geofence.

    The geofence's cylinder fits inside the flight area. Every waypoint, and
    the return climb to return_height_m, is inside the geofence by
    clearance_m.
    """
    distance, height = geofence
    area_distance, area_height = config["flight_area"]
    clearance = config["clearance"]
    name = "postconditions.stays_in_geofence"
    problems = []
    if distance > area_distance:
        problems.append(
            f"{name}.max_distance_m {distance!r} is outside the flight area's "
            f"max_distance_m {area_distance!r}"
        )
    if height > area_height:
        problems.append(
            f"{name}.max_height_m {height!r} is above the flight area's "
            f"max_height_m {area_height!r}"
        )
    # The return climbs to return_height_m from a waypoint below it, then flies
    # level to the base, so its highest point is the higher of the two. A
    # waypoint above it is checked on its own below.
    if config["return_height"] > height - clearance:
        problems.append(
            f"{name}.max_height_m {height!r} leaves no room for the return climb "
            f"to {config['return_height']!r} m with {clearance!r} m clearance"
        )
    for waypoint_id, point in waypoints:
        sideways = math.hypot(point["x"], point["y"])
        if sideways > distance - clearance:
            problems.append(
                f"{waypoint_id} is {sideways!r} m sideways from the base, outside "
                f"the geofence's {distance!r} m less {clearance!r} m clearance"
            )
        if point["z"] > height - clearance:
            problems.append(
                f"{waypoint_id} is {point['z']!r} m up, above the geofence's "
                f"{height!r} m less {clearance!r} m clearance"
            )
    return problems


# ---- Where waypoints may go --------------------------------------------------


def waypoint_bounds(config, geofence):
    """Return (radius, z_low, z_high, problems) for every waypoint.

    Without a geofence the waypoints stay in the flight area. With one they
    stay inside it by the configured clearance.
    """
    if geofence is None:
        radius, top = config["flight_area"]
        where = "the flight area"
    else:
        radius = geofence[0] - config["clearance"]
        top = geofence[1] - config["clearance"]
        where = "the geofence, less its clearance,"
    if config["z_max"] is not None:
        top = min(top, config["z_max"])

    problems = []
    clear_of_base = 2 * config["zone"][0]
    if radius <= clear_of_base:
        problems.append(
            f"{where} reaches {radius!r} m from the base, but a waypoint must "
            f"be more than {clear_of_base!r} m from it"
        )
    if config["z_min"] > top:
        problems.append(
            f"waypoints must be at least {config['z_min']!r} m up, but {where} "
            f"allows at most {top!r} m"
        )
    return radius, config["z_min"], top, problems


def _draw(rng, low, high):
    # uniform() can round past high by a tiny amount. Clamping keeps the value
    # inside the inclusive bounds.
    return min(max(rng.uniform(low, high), low), high)


def draw_waypoints(count, bounds, zone, rng):
    """Return [(id, point), ...]: count waypoints inside the cylinder, spaced apart.

    A draw that breaks waypoint_spacing is drawn again.
    """
    radius, z_low, z_high = bounds
    waypoints = []
    for number in range(1, count + 1):
        for _ in range(MAX_DRAWS):
            point = {
                "x": rng.uniform(-radius, radius),
                "y": rng.uniform(-radius, radius),
                "z": _draw(rng, z_low, z_high),
            }
            if math.hypot(point["x"], point["y"]) > radius:
                continue  # outside the cylinder
            candidate = [*waypoints, (f"W{number}", point)]
            if not spacing_problems(candidate, zone):
                waypoints = candidate
                break
        else:
            raise GeneratorError(
                "settings",
                [
                    f"W{number} could not be placed apart from the base and the "
                    f"other waypoints in {MAX_DRAWS} draws"
                ],
            )
    return waypoints


# ---- Environment template ----------------------------------------------------


def load_states(template_path):
    """Return {"start": env, "goal": env}, checked copies of the two templates.

    A <mission> uses its first and last <env>, a single <env> is used for both.
    Each copy keeps only the properties in PROPERTIES, and has its ids filled
    by _link_ids, so the input is never changed.
    """
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        root = ET.parse(template_path, parser=parser).getroot()
    except ET.ParseError as e:
        raise GeneratorError(template_path, [f"not valid XML: {e}"]) from None

    if root.tag == "env":
        # One template for both states: check and clean it once, then copy it,
        # so the goal can be filled without changing the start. Its id, if it
        # has one, is the start's, and the goal gets its own.
        start, problems = _checked_copy(root, "env")
        goal = copy.deepcopy(start)
        goal.set("id", "")
    elif root.tag == "mission":
        envs = root.findall("env")  # direct children only, not nested <env>s
        if len(envs) < 2:
            raise GeneratorError(
                template_path,
                [f"<mission> has {len(envs)} <env>, expected at least two"],
            )
        # PLACEHOLDER: the start and goal states are chosen by position (the
        # first and last <env>), not by id, until the team confirms.
        start, start_problems = _checked_copy(envs[0], _label("start", envs[0]))
        goal, goal_problems = _checked_copy(envs[-1], _label("goal", envs[-1]))
        problems = start_problems + goal_problems
    else:
        raise GeneratorError(
            template_path, [f"root is <{root.tag}>, expected <mission> or <env>"]
        )
    if not problems:
        problems = _link_ids(start, goal)
    if problems:
        raise GeneratorError(template_path, problems)
    return {"start": start, "goal": goal}


def _blank(value):
    return value is None or not value.strip()


def _link_ids(start, goal):
    """Fill the blank ids in both states, and return what doesn't match.

    The two states get distinct ids. The agent and the base each have one id
    in both, and the agent's base attribute names the base's id. Its
    no_fly_zone attribute is dropped, since no <no_fly_zone> is written. An id
    the template supplies is kept.
    """
    states = {"start": start, "goal": goal}
    found = {"agent": [], "base": []}
    for role, env in states.items():
        agent = env.find("agent")
        found["agent"].append((f"the {role} state's <agent id>", agent.get("id")))
        found["base"].append(
            (f"the {role} state's <base id>", env.find("base").get("id"))
        )
        found["base"].append((f"the {role} state's <agent base>", agent.get("base")))

    problems = []
    ids = {}
    for part, supplied in found.items():
        given = [(where, value) for where, value in supplied if not _blank(value)]
        if len({value for _, value in given}) > 1:
            listed = ", ".join(f"{where} is {value!r}" for where, value in given)
            problems.append(f"the {part} needs one id in both states, but {listed}")
        ids[part] = given[0][1] if given else DEFAULT_IDS[part]
    for role, env in states.items():
        ids[role] = DEFAULT_IDS[role] if _blank(env.get("id")) else env.get("id")
    if ids["start"] == ids["goal"]:
        problems.append(
            f"the start and goal states both have id {ids['start']!r}, but need "
            "distinct ids"
        )
    if problems:
        return problems

    for role, env in states.items():
        env.set("id", ids[role])
        env.find("base").set("id", ids["base"])
        agent = env.find("agent")
        agent.set("id", ids["agent"])
        agent.set("base", ids["base"])
        agent.attrib.pop("no_fly_zone", None)
    return problems


def _checked_copy(template, label):
    """Return (env, problems): a cleaned copy of template, and what it lacks."""
    env = copy.deepcopy(template)
    env.tail = None  # the text after the <env> in a <mission> file
    return env, [f"{label}: {problem}" for problem in _shape(env)]


def _label(role, env):
    env_id = env.get("id")
    return f'{role} <env id="{env_id}">' if env_id else f"{role} <env>"


def _keep_only(parent, tags):
    """Remove every child element of parent whose tag is not in tags.

    A comment on the same line as a removed element goes with it.
    """
    children = list(parent)
    for index, child in enumerate(children):
        if child.tag is ET.Comment or child.tag in tags:
            continue
        parent.remove(child)
        after = children[index + 1] if index + 1 < len(children) else None
        if after is not None and after.tag is ET.Comment:
            if "\n" not in (child.tail or ""):
                parent.remove(after)


def _shape(env):
    """Leave only the README's properties in env, and report the missing ones.

    Only the first <waypoint> is checked: it is the pattern for every
    generated waypoint, and the others are replaced.
    """
    problems = []
    _keep_only(env, PROPERTIES)
    for tag, properties in PROPERTIES.items():
        found = env.findall(tag)
        if tag == "waypoint" and not found:
            problems.append("<env> has no <waypoint>")
            continue
        if tag != "waypoint" and len(found) != 1:
            problems.append(f"<env> has {len(found)} <{tag}>, expected one")
            continue
        part = found[0]  # the one <base> or <agent>, or the first <waypoint>
        where = f"<{tag}>"
        _keep_only(part, properties)
        for prop in properties:
            children = part.findall(prop)
            if prop == "vehicle_type" and prop in part.attrib:
                # vehicle_type on the <agent> tag, as the team template has it.
                if children:
                    problems.append(
                        f"{where} has a {prop} attribute and a <{prop}>, expected one"
                    )
                continue
            if len(children) != 1:
                problems.append(f"{where} has {len(children)} <{prop}>, expected one")
                continue
            element = children[0]
            if prop != "velocity":
                if "value" not in element.attrib:
                    problems.append(f"{where} <{prop}> has no value")
                continue
            _keep_only(element, AXES)
            for axis in AXES:
                speed = element.find(axis)
                if speed is None:
                    problems.append(f"{where} <velocity> has no <{axis}>")
                elif "value" not in speed.attrib:
                    problems.append(f"{where} <velocity> <{axis}> has no value")
    return problems


def _bool(value):
    return "true" if value else "false"


def _fill(env, waypoints, vehicle, visited):
    """Set every generated value in env, a checked copy of a template."""
    vehicle_name, flags = vehicle
    base, agent = env.find("base"), env.find("agent")
    velocity = agent.find("velocity")
    # The agent starts at its base, landed and at rest, and ends there.
    for axis in AXES:
        base.find(axis).set("value", str(BASE_POSITION[axis]))
        agent.find(axis).set("value", str(BASE_POSITION[axis]))
        velocity.find(axis).set("value", "0")
    agent.find("landed").set("value", "true")
    if "vehicle_type" in agent.attrib:
        agent.set("vehicle_type", vehicle_name)  # the team template's <agent> tag
    else:
        agent.find("vehicle_type").set("value", vehicle_name)  # the M01 fixture's
    for flag in EQUIPMENT:
        agent.find(flag).set("value", _bool(flags[flag]))

    pattern, *others = env.findall("waypoint")
    position = list(env).index(pattern)
    for element in (pattern, *others):
        env.remove(element)
    for offset, (waypoint_id, point) in enumerate(waypoints):
        waypoint = copy.deepcopy(pattern)
        waypoint.set("id", waypoint_id)
        for axis in AXES:
            waypoint.find(axis).set("value", repr(point[axis]))
        waypoint.find("visited").set("value", _bool(visited))
        env.insert(position + offset, waypoint)
    ET.indent(env, space="  ")


# ---- Generation and output ---------------------------------------------------


def generate(template_path, settings_path, config_path, seed):
    """Return {"mission": dict, "start": tree, "goal": tree} for one seed."""
    config = load_config(config_path)
    settings = load_settings(settings_path, config)
    states = load_states(template_path)
    *bounds, problems = waypoint_bounds(config, settings["geofence"])
    if problems:
        raise GeneratorError(f"{settings_path} and {config_path}", problems)

    rng = random.Random(seed)
    try:
        waypoints = draw_waypoints(settings["waypoints"], bounds, config["zone"], rng)
    except GeneratorError as e:
        raise GeneratorError(settings_path, e.problems) from None

    # Check the drawn mission against both preconditions before anything is
    # written. The geofence check is skipped for a mission without one.
    # PLACEHOLDER: preconditions.tasks (plan_exists) waits for the plan step.
    problems = spacing_problems(waypoints, config["zone"])
    if settings["geofence"] is not None:
        problems += geofence_problems(waypoints, settings["geofence"], config)
    if problems:
        raise GeneratorError(settings_path, problems)

    result = {
        "mission": {
            "mission_id": settings["mission_id"],
            "start": "start.xml",
            "goal": "goal.xml",
            "postconditions": settings["postconditions"],
            # PLACEHOLDER: the README says generated missions carry their
            # settings and seed, but not under which keys.
            "seed": seed,
            "settings": settings["raw"],
        }
    }
    for name, visited in (("start", False), ("goal", True)):
        _fill(states[name], waypoints, config["vehicle"], visited)
        result[name] = ET.ElementTree(states[name])
    return result


def to_xml(tree):
    return ET.tostring(tree.getroot(), encoding="unicode") + "\n"


class _MissionDumper(yaml.SafeDumper):
    """Serialize mission metadata in the M01 fixture's format.

    List items are indented under their key, and each postcondition's fields
    are on one line, as in `- hold_at: {waypoint: W1, min_s: 5}`.
    """

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


class _OneLine(dict):
    pass


_MissionDumper.add_representer(
    _OneLine,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True
    ),
)


def to_yaml(mission):
    mission = dict(mission)
    mission["postconditions"] = [
        {name: _OneLine(fields) for name, fields in item.items()}
        for item in mission["postconditions"]
    ]
    return yaml.dump(
        mission, Dumper=_MissionDumper, sort_keys=False, default_flow_style=None
    )


def write_outputs(result, output_dir, inputs):
    """Write start.xml and goal.xml to output_dir.

    Refuses, before writing anything, an output path that is one of inputs.
    Both files are written to temporary names before either is renamed.
    """
    output_dir = Path(output_dir)
    texts = {
        "start.xml": to_xml(result["start"]),
        "goal.xml": to_xml(result["goal"]),
    }
    paths = {name: output_dir / name for name in texts}
    clashes = [
        f"{path} is the input file {source}, which is never overwritten"
        for path in paths.values()
        for source in inputs
        if path.exists() and path.samefile(source)
    ]
    if clashes:
        raise GeneratorError(output_dir, clashes)

    created = not output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = {name: output_dir / f".{name}.partial" for name in texts}
    try:
        for name, text in texts.items():
            temporary[name].write_text(text, encoding="utf-8")
    except OSError:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        if created:
            output_dir.rmdir()
        raise
    for name in texts:
        os.replace(temporary[name], paths[name])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate start.xml and goal.xml for one mission."
    )
    parser.add_argument("template", type=Path, help="environment template (XML)")
    parser.add_argument("settings", type=Path, help="mission settings (simple.yaml)")
    parser.add_argument("config", type=Path, help="platform config (px4.yaml)")
    parser.add_argument("--seed", type=int, help="random seed (drawn if omitted)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="directory for the state files (default: current directory)",
    )
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else secrets.randbits(32)
    inputs = (args.template, args.settings, args.config)
    try:
        result = generate(*inputs, seed)
        write_outputs(result, args.output_dir, inputs)
    except (GeneratorError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"seed: {seed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
