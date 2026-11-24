"""Load platform_configs/px4.yaml and follow its names to values.

A value in the config can be a name that starts with one of the config's own sections,
such as `tolerances.at_waypoint.within_m` or `base_lat_lon.lat`. It means "use the
value found there" (the file's header, "How values are written").
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "platform_configs" / "px4.yaml"


def load_config(path=DEFAULT_CONFIG):
    with open(path) as f:
        return yaml.safe_load(f)


def is_config_name(config, value):
    """True if `value` is a dotted name starting with one of the config's sections."""
    return isinstance(value, str) and "." in value and value.split(".", 1)[0] in config


def follow(config, name):
    """The value a config name points to: `tolerances.at_waypoint.within_m` -> 2."""
    node = config
    for part in name.split("."):
        node = node[part]
    return node
