from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AgentState,
    BaseState,
    CrossCheckData,
    EnvState,
    Mission,
    PostconditionSpec,
    Readings,
    TimedBool,
    TimedInt,
    TimedVec3,
    WaypointState,
)


def _parse_typed_elem(elem: ET.Element | None) -> Any:
    if elem is None:
        return None
    raw_val = elem.attrib["value"]
    val_type = elem.attrib.get("type", "string")
    if val_type == "float":
        return float(raw_val)
    if val_type == "int":
        return int(raw_val)
    if val_type == "bool":
        lowered = raw_val.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise ValueError(f"Invalid bool value '{raw_val}' in <{elem.tag}>")
    return raw_val


def load_env_xml(path: Path) -> EnvState:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "env":
        raise ValueError(f"Expected <env> root in {path}, got <{root.tag}>")

    base_el = root.find("base")
    if base_el is None:
        raise ValueError(f"Missing <base> in {path}")
    base = BaseState(
        id=base_el.attrib["id"],
        x=float(_parse_typed_elem(base_el.find("x"))),
        y=float(_parse_typed_elem(base_el.find("y"))),
        z=float(_parse_typed_elem(base_el.find("z"))),
    )

    agent_el = root.find("agent")
    if agent_el is None:
        raise ValueError(f"Missing <agent> in {path}")
    vel_el = agent_el.find("velocity")
    agent = AgentState(
        id=agent_el.attrib["id"],
        base_id=agent_el.attrib.get("base"),
        x=_parse_typed_elem(agent_el.find("x")),
        y=_parse_typed_elem(agent_el.find("y")),
        z=_parse_typed_elem(agent_el.find("z")),
        vx=_parse_typed_elem(vel_el.find("x")) if vel_el is not None else None,
        vy=_parse_typed_elem(vel_el.find("y")) if vel_el is not None else None,
        vz=_parse_typed_elem(vel_el.find("z")) if vel_el is not None else None,
        landed=_parse_typed_elem(agent_el.find("landed")),
        vehicle_type=_parse_typed_elem(agent_el.find("vehicle_type")),
        has_camera=_parse_typed_elem(agent_el.find("has_camera")),
        has_grippers=_parse_typed_elem(agent_el.find("has_grippers")),
    )

    waypoints: dict[str, WaypointState] = {}
    for wp_el in root.findall("waypoint"):
        wp_id = wp_el.attrib["id"]
        waypoints[wp_id] = WaypointState(
            id=wp_id,
            x=float(_parse_typed_elem(wp_el.find("x"))),
            y=float(_parse_typed_elem(wp_el.find("y"))),
            z=float(_parse_typed_elem(wp_el.find("z"))),
            visited=_parse_typed_elem(wp_el.find("visited")),
            clicked_pic=_parse_typed_elem(wp_el.find("clicked_pic")),
        )

    return EnvState(
        id=root.attrib.get("id", ""),
        env_type=root.attrib.get("type", ""),
        base=base,
        agent=agent,
        waypoints=waypoints,
    )


def load_mission(mission_path: Path) -> tuple[Mission, EnvState, EnvState]:
    with mission_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    postconditions: list[PostconditionSpec] = []
    for item in raw.get("postconditions") or []:
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError(
                f"Each postcondition must be a single-key mapping, got: {item!r}"
            )
        name, params = next(iter(item.items()))
        postconditions.append(PostconditionSpec(name=name, params=dict(params or {})))

    mission = Mission(
        mission_id=str(raw["mission_id"]),
        start_path=str(raw["start"]),
        goal_path=str(raw["goal"]),
        postconditions=tuple(postconditions),
    )

    base_dir = mission_path.parent
    start_state = load_env_xml(base_dir / mission.start_path)
    goal_state = load_env_xml(base_dir / mission.goal_path)
    return mission, start_state, goal_state


def load_readings(path: Path) -> Readings:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    cross_check: CrossCheckData | None = None
    if "cross_check" in raw and raw["cross_check"] is not None:
        cc = raw["cross_check"]
        raw_pubs = cc.get("publishers")
        if isinstance(raw_pubs, list):
            publishers: int | None = len(raw_pubs)
        elif raw_pubs is not None:
            publishers = int(raw_pubs)
        else:
            publishers = None
        cross_check = CrossCheckData(
            verdict=str(cc["verdict"]),
            recording=cc.get("recording"),
            compared=int(cc.get("compared", 0)),
            unmatched=int(cc.get("unmatched", 0)),
            over_limit=int(cc.get("over_limit", 0)),
            max_difference_m=(
                float(cc["max_difference_m"])
                if cc.get("max_difference_m") is not None
                else None
            ),
            publishers=publishers,
            reason=cc.get("reason"),
        )

    return Readings(
        mission_id=str(raw["mission_id"]),
        run_id=str(raw["run_id"]),
        run_status=str(raw["run_status"]),
        reason=raw.get("reason"),
        position=tuple(
            TimedVec3(float(r["t_s"]), float(r["x"]), float(r["y"]), float(r["z"]))
            for r in raw.get("position", [])
        ),
        velocity=tuple(
            TimedVec3(float(r["t_s"]), float(r["x"]), float(r["y"]), float(r["z"]))
            for r in raw.get("velocity", [])
        ),
        landed=tuple(
            TimedBool(float(r["t_s"]), bool(r["value"])) for r in raw.get("landed", [])
        ),
        nav_state=tuple(
            TimedInt(float(r["t_s"]), int(r["value"])) for r in raw.get("nav_state", [])
        ),
        arming_state=tuple(
            TimedInt(float(r["t_s"]), int(r["value"]))
            for r in raw.get("arming_state", [])
        ),
        disarm_reason=tuple(
            TimedInt(float(r["t_s"]), int(r["value"]))
            for r in raw.get("disarm_reason", [])
        ),
        camera_triggered_at=tuple(
            float(r["t_s"]) for r in raw.get("camera_triggered_at", [])
        ),
        camera_trigger_mode=(
            int(raw["camera_trigger_mode"])
            if raw.get("camera_trigger_mode") is not None
            else None
        ),
        time_zero_us=(
            int(raw["time_zero_us"]) if raw.get("time_zero_us") is not None else None
        ),
        sources=raw.get("sources"),
        missing_topics=tuple(raw.get("missing_topics", [])),
        cross_check=cross_check,
    )
