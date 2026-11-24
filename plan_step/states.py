"""Read a mission's start and goal states (start.xml, goal.xml) into flat dictionaries.

A state becomes {"base.x": 0.0, "agent.landed": True, "agent.velocity.x": 0.0,
"waypoint.W1.visited": False, ...}: one key per property, written the way
platform_configs/px4.yaml names them, with the waypoint's id added after `waypoint.`.
"""

# The state files are ours (the generator writes them). The standard library's parser
# doesn't fetch external entities, so it is safe for them without another dependency.
import math
import xml.etree.ElementTree as ET

_BOOLS = {"true": True, "false": False, "1": True, "0": False}


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        # inf and nan read as floats, but no position or speed can be either, and the
        # .plan file would hold JSON that isn't valid.
        raise ValueError(f"{text!r} isn't a finite number")
    return value


# The XML `type` attribute says how to read `value`.
_READERS = {
    "float": _finite_float,
    "double": _finite_float,
    "int": int,
    "string": str,
    "bool": lambda text: _BOOLS[text.strip().lower()],
}


class StateError(ValueError):
    """A state file we can't read. The message says which file and property."""


# What each property must be, by the last part of its name: the XML types it may have,
# and its unit. Positions are in metres and speeds in m/s
# (tests/fixtures/m01/README.md). Any other unit is refused, so a height given in cm
# can't be flown as metres. A property not listed here is read as its type says.
_NUMBER = ("float", "double", "int")
_KINDS = {
    "x": (_NUMBER, "m"),
    "y": (_NUMBER, "m"),
    "z": (_NUMBER, "m"),
    "landed": (("bool",), None),
    "visited": (("bool",), None),
    "clicked_pic": (("bool",), None),
    "has_camera": (("bool",), None),
    "has_grippers": (("bool",), None),
    "vehicle_type": (("string",), None),
}
_SPEED = (_NUMBER, "m/s")  # agent.velocity.x, .y and .z
_SAY = {
    _NUMBER: "a number",
    ("bool",): "true or false (bool)",
    ("string",): "text (string)",
}


# What every state file lists, start and goal alike (tests/fixtures/m01/README.md). A
# waypoint's clicked_pic may be left out: it then counts as false.
REQUIRED = (
    "base.x",
    "base.y",
    "base.z",
    "agent.x",
    "agent.y",
    "agent.z",
    "agent.velocity.x",
    "agent.velocity.y",
    "agent.velocity.z",
    "agent.landed",
    "agent.vehicle_type",
    "agent.has_camera",
    "agent.has_grippers",
)
REQUIRED_PER_WAYPOINT = ("x", "y", "z", "visited")


def read_state(path):
    """Every property in one state file, as {name: value}."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise StateError(f"can't read {path.name}: {error}") from error
    return _state(root, path.name)


def read_state_xml(source, name):
    """The same for a state held in memory: XML text, an Element or an ElementTree.

    `name` is what the messages call it, such as start.xml.
    """
    if isinstance(source, ET.ElementTree):
        source = source.getroot()
    if isinstance(source, str):
        try:
            source = ET.fromstring(source)
        except ET.ParseError as error:
            raise StateError(f"can't read {name}: {error}") from error
    if not isinstance(source, ET.Element):
        raise StateError(f"{name} should be XML text or an XML element")
    return _state(source, name)


def _state(root, file_name):
    state = {}
    seen = set()
    for thing in root:
        if thing.tag == "waypoint":
            if "id" not in thing.attrib:
                raise StateError(f"{file_name}: a waypoint has no id")
            wp = thing.attrib["id"]
            if wp in seen:
                raise StateError(f"{file_name}: two waypoints have the id {wp!r}")
            seen.add(wp)
            if not len(thing):
                # An empty waypoint adds no properties, so it would drop out unnoticed.
                raise StateError(f"{file_name}: waypoint {wp} lists no properties")
            prefix = f"waypoint.{wp}"
        else:  # base, agent: one of each
            prefix = thing.tag
        _read_properties(thing, prefix, state, file_name)
        if thing.tag == "agent" and "vehicle_type" in thing.attrib:
            # #16's template puts it on the tag: <agent vehicle_type="...">.
            if "agent.vehicle_type" in state:
                raise StateError(
                    f"{file_name}: agent gives vehicle_type twice, on the <agent> "
                    "tag and as <vehicle_type>"
                )
            if not thing.attrib["vehicle_type"].strip():
                raise StateError(f"{file_name}: agent.vehicle_type is empty")
            state["agent.vehicle_type"] = thing.attrib["vehicle_type"]
    return state


def _read_properties(element, prefix, state, file_name):
    for child in element:
        name = f"{prefix}.{child.tag}"
        if len(child):  # a group such as <velocity> with <x>, <y>, <z> inside
            _read_properties(child, name, state, file_name)
            continue
        if name in state:
            # Refused, because here the second value would win while another reader
            # could keep the first.
            raise StateError(f"{file_name}: {name} is given twice")
        # Every property needs a type and a value, or it could be skipped unnoticed.
        kind, text = child.attrib.get("type"), child.attrib.get("value")
        if kind is None or text is None:
            raise StateError(f"{file_name}: {name} needs both a type and a value")
        if kind not in _READERS:
            raise StateError(f"{file_name}: {name} has an unknown type {kind!r}")
        _check_kind(child, name, kind, file_name)
        try:
            state[name] = _READERS[kind](text)
        except (KeyError, ValueError) as error:
            what = "finite number" if _READERS[kind] is _finite_float else kind
            raise StateError(
                f"{file_name}: {name} = {text!r} isn't a {what}"
            ) from error


def _check_kind(child, name, kind, file_name):
    """The property's type and unit must be the ones it is defined with."""
    expected = _SPEED if ".velocity." in name else _KINDS.get(name.rsplit(".", 1)[-1])
    if expected is None:
        return
    kinds, unit = expected
    if kind not in kinds:
        raise StateError(f"{file_name}: {name} should be {_SAY[kinds]}, not {kind!r}")
    got = child.attrib.get("unit")
    if unit is not None and got != unit:
        how = f"not {got!r}" if got is not None else "but has no unit"
        raise StateError(f"{file_name}: {name} should be in {unit}, {how}")


def missing_properties(state):
    """The properties every state lists that this one leaves out, in REQUIRED order."""
    names = list(REQUIRED)
    for wp in waypoint_ids(state):
        names += [f"waypoint.{wp}.{prop}" for prop in REQUIRED_PER_WAYPOINT]
    return [name for name in names if name not in state]


def waypoint_ids(state):
    """The waypoint ids in a state, in waypoint id order (W2 before W10)."""
    ids = {key.split(".")[1] for key in state if key.startswith("waypoint.")}
    # Ids that are equal as numbers (W01, W1) are then sorted as text, so the order is
    # always the same.
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
