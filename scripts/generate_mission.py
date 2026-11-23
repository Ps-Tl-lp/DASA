import argparse
import copy
import math
import random
import secrets
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

AXES = ("x", "y", "z")

# The only ranges the config may give, in the order the values are drawn.
RANGE_KEYS = [f"{thing}.{axis}" for thing in ("agent", "waypoint") for axis in AXES]


class GeneratorError(Exception):
    """A config, template or output path the generator cannot use."""

    def __init__(self, source, problems):
        self.problems = list(problems)
        lines = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{source}:\n{lines}")


# ---- Config ------------------------------------------------------------------


def load_ranges(config_path):
    """Return {"agent.x": (low, high), ...} for every key in RANGE_KEYS."""
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise GeneratorError(config_path, [f"not valid YAML: {e}"]) from None

    try:
        allowed = config["preconditions"]["allowed_values"]
    except (KeyError, TypeError):
        allowed = None
    if not isinstance(allowed, dict):
        raise GeneratorError(
            config_path, ["preconditions.allowed_values is missing or not a mapping"]
        )

    ranges, problems = {}, []
    for key in RANGE_KEYS:
        bounds, found = _parse_range(key, allowed)
        problems += found
        if bounds is not None:
            ranges[key] = bounds
    expected = ", ".join(RANGE_KEYS)
    for key in allowed:
        if key not in RANGE_KEYS:
            problems.append(f"{key} is not an allowed key (expected only {expected})")
    if problems:
        raise GeneratorError(config_path, problems)
    return ranges


def _parse_range(key, allowed):
    """Return ((low, high), []) or (None, problems)."""
    if key not in allowed:
        return None, [f"{key} has no range"]
    spec = allowed[key]
    if not isinstance(spec, dict):
        return None, [f"{key} should be {{ min: N, max: N }}, got {spec!r}"]

    problems = []
    for end in ("min", "max"):
        if end not in spec:
            problems.append(f"{key}.{end} is missing")
        elif not _is_number(spec[end]):
            shown = "blank" if spec[end] is None else repr(spec[end])
            problems.append(f"{key}.{end} is {shown}, not a number")
    if problems:
        return None, problems

    low, high = float(spec["min"]), float(spec["max"])
    if low > high:
        return None, [f"{key}: min {spec['min']} is greater than max {spec['max']}"]
    return (low, high), []


def _is_number(value):
    # YAML reads true/false as bools, and bool is a subclass of int.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(value)


def _check_overlap(ranges, geofence):
    """Report each range that leaves no value inside the geofence."""
    problems = []
    for key, (low, high) in ranges.items():
        axis = key.split(".")[-1]
        fence_low, fence_high = geofence[axis]
        if high < fence_low or low > fence_high:
            problems.append(
                f"{key} range [{low!r}, {high!r}] does not overlap the "
                f"geofence's {axis} [{fence_low!r}, {fence_high!r}]"
            )
    return problems


# ---- Environment file --------------------------------------------------------


def load_states(template_path):
    """Return ({"start": (env, parts), "goal": (env, parts)}, geofence).

    Each env is a fresh copy of its template, so the input is never changed.
    parts holds the elements in that copy that the generator fills. geofence
    is {"x": (min, max), ...}, read from the start template.
    """
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        root = ET.parse(template_path, parser=parser).getroot()
    except ET.ParseError as e:
        raise GeneratorError(template_path, [f"not valid XML: {e}"]) from None

    if root.tag == "env":
        start = goal = root
    elif root.tag == "mission":
        envs = root.findall("env")  # direct children only, not nested <env>s
        if len(envs) < 2:
            raise GeneratorError(
                template_path,
                [f"<mission> has {len(envs)} <env>, expected at least two"],
            )
        # PLACEHOLDER: the start and goal states are chosen by position (the
        # first and last <env>), not by id (S0 and Sg), until the team confirms.
        start, goal = envs[0], envs[-1]
    else:
        raise GeneratorError(
            template_path, [f"root is <{root.tag}>, expected <mission> or <env>"]
        )

    states, problems = {}, []
    for name, template in (("start", start), ("goal", goal)):
        env = copy.deepcopy(template)
        env.tail = None  # the text after the <env> in a <mission> file
        parts, found = _find_parts(env)
        if name == "start":
            geofence, fence_problems = _read_geofence(parts)
            found += fence_problems
        states[name] = (env, parts)
        if start is not goal:
            problems += [f"{_label(name, template)}: {problem}" for problem in found]
        elif name == "start":  # a single <env>: report its problems once
            problems += [f"env: {problem}" for problem in found]

    start_count = len(states["start"][1]["waypoints"])
    goal_count = len(states["goal"][1]["waypoints"])
    if start_count != goal_count:
        problems.append(
            f"the start state has {start_count} <waypoint> but the goal "
            f"state has {goal_count}"
        )
    if problems:
        raise GeneratorError(template_path, problems)
    return states, geofence


def _read_geofence(parts):
    """Return ({"x": (min, max), ...}, problems) from a template's <geofence>.

    Missing elements and attributes were already reported by _find_parts.
    """
    geofence, problems = {}, []
    for axis, element in parts.get("geofence", {}).items():
        bounds = []
        for end in ("min", "max"):
            text = element.get(end)
            if text is None:
                continue  # already reported
            try:
                value = float(text)
            except ValueError:
                value = math.nan
            if math.isfinite(value):
                bounds.append(value)
            else:
                shown = "blank" if text.strip() == "" else repr(text)
                problems.append(f"<geofence> <{axis}> {end} is {shown}, not a number")
        if len(bounds) == 2:
            low, high = bounds
            if low > high:
                problems.append(
                    f"<geofence> <{axis}>: min {element.get('min')} is greater "
                    f"than max {element.get('max')}"
                )
            geofence[axis] = (low, high)
    return geofence, problems


def _label(role, env):
    env_id = env.get("id")
    return f'{role} <env id="{env_id}">' if env_id else f"{role} <env>"


def _find_parts(env):
    """Return (parts, problems) for the elements in env the generator fills.

    Only direct children are searched at each level.
    """
    problems = []

    def one(parent, tag, where):
        found = parent.findall(tag)
        if len(found) != 1:
            problems.append(f"{where} has {len(found)} <{tag}>, expected one")
            return None
        return found[0]

    def axes(parent, where, attributes):
        elements = {}
        for axis in AXES:
            element = parent.find(axis)
            if element is None:
                problems.append(f"{where} has no <{axis}>")
                continue
            for name in attributes:
                if name not in element.attrib:
                    problems.append(f"{where} <{axis}> has no {name}")
            elements[axis] = element
        return elements

    parts = {"waypoints": []}
    geofence = one(env, "geofence", "<env>")
    if geofence is not None:
        parts["geofence"] = axes(geofence, "<geofence>", ("min", "max"))
    base = one(env, "base", "<env>")
    if base is not None:
        parts["base"] = axes(base, "<base>", ("value",))
    agent = one(env, "agent", "<env>")
    if agent is not None:
        parts["agent"] = axes(agent, "<agent>", ("value",))
        velocity = one(agent, "velocity", "<agent>")
        if velocity is not None:
            parts["velocity"] = axes(velocity, "<agent> <velocity>", ("value",))

    waypoints = env.findall("waypoint")
    if not waypoints:
        problems.append("<env> has no <waypoint>")
    for number, waypoint in enumerate(waypoints, start=1):
        where = f"<waypoint> #{number}"
        elements = axes(waypoint, where, ("value",))
        visited = one(waypoint, "visited", where)
        if visited is not None and "value" not in visited.attrib:
            problems.append(f"{where} <visited> has no value")
        elements["visited"] = visited
        parts["waypoints"].append(elements)
    return parts, problems


# ---- Generation --------------------------------------------------------------


def _draw(rng, low, high):
    # uniform() can round past high by a tiny amount. Clamping keeps the value
    # inside the inclusive bounds.
    return min(max(rng.uniform(low, high), low), high)


def draw_start(ranges, geofence, waypoint_count, rng):
    """Draw the agent, then every waypoint, inside the geofence."""

    def inside_geofence(thing):
        point = {}
        for axis in AXES:
            low, high = ranges[f"{thing}.{axis}"]
            fence_low, fence_high = geofence[axis]
            # Never empty: generate() checked the overlap.
            point[axis] = _draw(rng, max(low, fence_low), min(high, fence_high))
        return point

    agent = inside_geofence("agent")
    waypoints = [inside_geofence("waypoint") for _ in range(waypoint_count)]
    return {"agent": agent, "waypoints": waypoints}


def _fill(parts, values, fence_text, visited):
    for axis in AXES:
        low, high = fence_text[axis]
        parts["geofence"][axis].set("min", low)
        parts["geofence"][axis].set("max", high)
        # The agent starts at its base, and the goal has it back there.
        parts["base"][axis].set("value", repr(values["agent"][axis]))
        parts["agent"][axis].set("value", repr(values["agent"][axis]))
        parts["velocity"][axis].set("value", repr(0.0))  # at rest
    for elements, point in zip(parts["waypoints"], values["waypoints"], strict=True):
        for axis in AXES:
            elements[axis].set("value", repr(point[axis]))
        elements["visited"].set("value", "true" if visited else "false")


def generate(template_path, config_path, seed):
    """Return {"start": tree, "goal": tree} for one seed."""
    ranges = load_ranges(config_path)
    states, geofence = load_states(template_path)
    problems = _check_overlap(ranges, geofence)
    if problems:
        raise GeneratorError(f"{config_path} and {template_path}", problems)

    start_parts = states["start"][1]
    waypoint_count = len(start_parts["waypoints"])
    values = draw_start(ranges, geofence, waypoint_count, random.Random(seed))
    # The goal gets the start template's geofence exactly as written there.
    fence_text = {
        axis: (element.get("min"), element.get("max"))
        for axis, element in start_parts["geofence"].items()
    }

    trees = {}
    for name, (env, parts) in states.items():
        _fill(parts, values, fence_text, visited=(name == "goal"))
        trees[name] = ET.ElementTree(env)
    return trees


# ---- Output ------------------------------------------------------------------


def to_xml(tree):
    return ET.tostring(tree.getroot(), encoding="unicode") + "\n"


def write_states(trees, output_dir, inputs):
    """Write output_dir/<name>.xml for each tree.

    Refuses, before writing anything, an output path that is one of inputs.
    """
    output_dir = Path(output_dir)
    paths = {name: output_dir / f"{name}.xml" for name in trees}
    clashes = [
        f"{path} is the input file {source}, which is never overwritten"
        for path in paths.values()
        for source in inputs
        if path.exists() and path.samefile(source)
    ]
    if clashes:
        raise GeneratorError(output_dir, clashes)

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, tree in trees.items():
        paths[name].write_text(to_xml(tree), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path, help="environment file (XML)")
    parser.add_argument("config", type=Path, help="mission config (px4.yaml)")
    parser.add_argument("--seed", type=int, help="random seed (drawn if omitted)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="directory for start.xml and goal.xml (default: current directory)",
    )
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else secrets.randbits(32)
    try:
        trees = generate(args.template, args.config, seed)
        write_states(trees, args.output_dir, (args.template, args.config))
    except (GeneratorError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"seed: {seed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
