"""Read a mission's start and goal states (start.xml, goal.xml) into flat dictionaries.

A state becomes {"base.x": 0.0, "agent.landed": True, "agent.velocity.x": 0.0,
"waypoint.W1.visited": False, ...}: one key per property, written the way
platform_configs/px4.yaml names them, with the waypoint's id added after `waypoint.`.
"""

# The state files are ours (the generator writes them). The standard library's parser
# doesn't fetch external entities, so it is safe for them without another dependency.
import xml.etree.ElementTree as ET

_BOOLS = {"true": True, "false": False, "1": True, "0": False}

# The XML `type` attribute says how to read `value`.
_READERS = {
    "float": float,
    "double": float,
    "int": int,
    "string": str,
    "bool": lambda text: _BOOLS[text.strip().lower()],
}


class StateError(ValueError):
    """A state file we can't read. The message says which file and property."""


def read_state(path):
    """Every property in one state file, as {name: value}."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise StateError(f"can't read {path.name}: {error}") from error
    state = {}
    for thing in root:
        if thing.tag == "waypoint":
            if "id" not in thing.attrib:
                raise StateError(f"{path.name}: a waypoint has no id")
            prefix = f"waypoint.{thing.attrib['id']}"
        else:  # base, agent: one of each
            prefix = thing.tag
        _read_properties(thing, prefix, state, path.name)
    return state


def _read_properties(element, prefix, state, file_name):
    for child in element:
        name = f"{prefix}.{child.tag}"
        if len(child):  # a group such as <velocity> with <x>, <y>, <z> inside
            _read_properties(child, name, state, file_name)
            continue
        # A leaf must say its type and value, or the plan could silently miss it.
        kind, text = child.attrib.get("type"), child.attrib.get("value")
        if kind is None or text is None:
            raise StateError(f"{file_name}: {name} needs both a type and a value")
        if kind not in _READERS:
            raise StateError(f"{file_name}: {name} has an unknown type {kind!r}")
        try:
            state[name] = _READERS[kind](text)
        except (KeyError, ValueError) as error:
            raise StateError(
                f"{file_name}: {name} = {text!r} isn't a {kind}"
            ) from error


def waypoint_ids(state):
    """The waypoint ids in a state, in waypoint id order (W2 before W10)."""
    ids = {key.split(".")[1] for key in state if key.startswith("waypoint.")}
    # Ids that compare equal as numbers (W01, W1) fall back to plain text order, so
    # the order never depends on chance.
    return sorted(ids, key=lambda wp: (_natural_key(wp), wp))


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
