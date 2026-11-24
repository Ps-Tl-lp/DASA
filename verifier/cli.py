from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

import yaml

from .config import load_config
from .engine import verify
from .loaders import load_mission, load_readings
from .validation import VerifierInputError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verifier",
        description=(
            "Verify normalized flight readings against a mission and platform config."
        ),
    )
    parser.add_argument(
        "mission",
        type=Path,
        help="The mission: its folder, its settings file, or an older mission.yaml",
    )
    parser.add_argument("readings", type=Path, help="Path to readings.json")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("platform_configs/px4.yaml"),
        help="Path to platform config YAML (default: platform_configs/px4.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for verdict.json (prints to stdout if omitted)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        mission, start_state, goal_state = load_mission(args.mission)
        readings = load_readings(args.readings)
        verdict = verify(mission, start_state, goal_state, readings, config)
    except (
        FileNotFoundError,
        KeyError,
        ValueError,
        VerifierInputError,
        yaml.YAMLError,
        json.JSONDecodeError,
        ET.ParseError,
    ) as exc:
        print(f"verifier error: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(verdict.to_dict(), indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0
