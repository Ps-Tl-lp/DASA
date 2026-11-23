"""Read a mission's start and goal states (start.xml, goal.xml) into flat dictionaries.

A state becomes {"base.x": 0.0, "agent.landed": True, "agent.velocity.x": 0.0,
"waypoint.W1.visited": False, ...}: one key per property, written the way
platform_configs/px4.yaml names them, with the waypoint's id added after `waypoint.`.
"""

# The state files are ours (the generator writes them). The standard library's parser
# doesn't fetch external entities, so it is safe for them without another dependency.
import xml.etree.ElementTree as ET

# The XML `type` attribute says how to read `value`.
_READERS = {
    "float": float,
    "int": int,
    "string": str,
    "bool": lambda text: {"true": True, "false": False}[text.strip().lower()],
}


def read_state(path):
    """Every property in one state file, as {name: value}."""
    root = ET.parse(path).getroot()
    state = {}
    for thing in root:
        if thing.tag == "waypoint":
            prefix = f"waypoint.{thing.attrib['id']}"
        else:  # base, agent: one of each
            prefix = thing.tag
        _read_properties(thing, prefix, state)
    return state


def _read_properties(element, prefix, state):
    for child in element:
        name = f"{prefix}.{child.tag}"
        if "value" in child.attrib:
            state[name] = _READERS[child.attrib.get("type", "string")](
                child.attrib["value"]
            )
        else:  # a group such as <velocity> with <x>, <y>, <z> inside
            _read_properties(child, name, state)


def waypoint_ids(state):
    """The waypoint ids in a state, in waypoint id order (W2 before W10)."""
    ids = {key.split(".")[1] for key in state if key.startswith("waypoint.")}
    return sorted(ids, key=_natural_key)


def _natural_key(text):
    # "W10" sorts after "W2": compare the digit runs as numbers.
    parts, digits = [], ""
    for ch in text:
        if ch.isdigit():
            digits += ch
            continue
        if digits:
            parts.append((1, int(digits)))
            digits = ""
        parts.append((0, ch))
    if digits:
        parts.append((1, int(digits)))
    return parts
