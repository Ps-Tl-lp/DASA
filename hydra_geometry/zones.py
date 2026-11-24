from __future__ import annotations

import math
from typing import Protocol


class HasXYZ(Protocol):
    x: float
    y: float
    z: float


def at_waypoint(
    pos: HasXYZ,
    waypoint: HasXYZ,
    within_m: float,
    height_within_m: float,
    edge_counts_as_inside: bool = True,
) -> bool:
    """Return True if pos is inside the waypoint's cylindrical zone."""
    horiz = math.hypot(pos.x - waypoint.x, pos.y - waypoint.y)
    vert = abs(pos.z - waypoint.z)
    if edge_counts_as_inside:
        return (horiz <= within_m or math.isclose(horiz, within_m)) and (
            vert <= height_within_m or math.isclose(vert, height_within_m)
        )
    return (horiz < within_m and not math.isclose(horiz, within_m)) and (
        vert < height_within_m and not math.isclose(vert, height_within_m)
    )


def inside_geofence(
    pos: HasXYZ,
    base: HasXYZ,
    max_distance_m: float,
    max_height_m: float,
    clearance_m: float = 0.0,
    edge_counts_as_inside: bool = True,
) -> bool:
    """Return True if pos is inside the geofence cylinder around base.

    The generator passes tolerances.geofence_clearance_m; the verifier passes 0.0.
    """
    horiz_limit = max_distance_m - clearance_m
    height_limit = max_height_m - clearance_m
    horiz = math.hypot(pos.x - base.x, pos.y - base.y)
    height = pos.z - base.z
    if edge_counts_as_inside:
        return (horiz <= horiz_limit or math.isclose(horiz, horiz_limit)) and (
            height <= height_limit or math.isclose(height, height_limit)
        )
    return (horiz < horiz_limit and not math.isclose(horiz, horiz_limit)) and (
        height < height_limit and not math.isclose(height, height_limit)
    )


def zones_apart(
    a: HasXYZ,
    b: HasXYZ,
    within_m: float,
    height_within_m: float,
) -> bool:
    """Return True if two waypoint zones do not overlap."""
    horiz = math.hypot(a.x - b.x, a.y - b.y)
    vert = abs(a.z - b.z)
    return horiz > 2.0 * within_m or vert > 2.0 * height_within_m
