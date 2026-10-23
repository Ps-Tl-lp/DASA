import argparse
import json
import math
from bisect import bisect_right
from pathlib import Path

PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"
DEFAULT_MAX_GAP = 1.0  # seconds; also bounds launch-position age


# Small validation and distance helpers


def finite(value):
    """Check whether a value is a finite number, excluding booleans.

    Args: value (object), the value to inspect.
    Returns: bool, True for a finite int or float.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def coordinates(lat, lon):
    """Check that latitude/longitude are finite and within geographic bounds.

    Args: lat (object), degrees from -90 to 90; lon (object), degrees from -180 to 180.
    Returns: bool, whether both coordinates are valid.
    """
    return finite(lat) and finite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def distance_m(lat1, lon1, lat2, lon2):
    """Calculate horizontal haversine distance on a spherical Earth.

    Args: lat1, lon1 (int | float), first location in degrees;
        lat2, lon2 (int | float), second location in degrees.
    Returns: float, distance in meters, excluding altitude.
    """
    latitude1 = math.radians(lat1)
    latitude2 = math.radians(lat2)
    longitude_change = math.radians(lon2 - lon1)
    haversine = math.sin((latitude2 - latitude1) / 2) ** 2
    haversine += (
        math.cos(latitude1) * math.cos(latitude2) * math.sin(longitude_change / 2) ** 2
    )
    return 6371000.0 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


# Read the planned requirements and recorded telemetry


def parse_waypoint(item, order, issues):
    """Extract a command-16 waypoint and flag invalid or unsupported fields.

    Args: item (dict), plan SimpleItem; order (int), one-based mission position;
        issues (list[str]), list to append validation messages to.
    Returns: dict of waypoint fields, or None if params are incomplete.
    """
    params = item.get("params", [])
    if not isinstance(params, list) or len(params) < 7:
        issues.append(f"Item {order}: waypoint params are incomplete")
        return None

    waypoint = dict(
        order=order,
        frame=item.get("frame"),
        dwell=params[0],
        lat=params[4],
        lon=params[5],
        alt=params[6],
    )
    if not coordinates(waypoint["lat"], waypoint["lon"]):
        issues.append(f"Item {order}: waypoint coordinates are unspecified or invalid")
    if not finite(waypoint["alt"]):
        issues.append(f"Item {order}: altitude is unspecified or invalid")
    if not finite(waypoint["dwell"]) or waypoint["dwell"] < 0:
        issues.append(f"Item {order}: dwell is unspecified or invalid")
    if waypoint["frame"] not in (0, 3):
        issues.append(f"Item {order}: unsupported altitude frame {waypoint['frame']}")
    if item.get("autoContinue", True) is not True:
        issues.append(f"Item {order}: manual continuation is unsupported")
    if params[2] not in (None, 0):
        issues.append(
            f"Item {order}: nonzero pass radius/fly-through behavior is unsupported"
        )
    return waypoint


def parse_mission(plan):
    """Extract ordered requirements without treating other commands as waypoints.

    Args: plan (dict), decoded QGroundControl plan with a mission object.
    Returns: dict with home (list or None), waypoints (ordered dictionaries),
        takeoffs (separate items), and issues (list[str]). Waypoints contain
        order, frame, lat/lon in degrees, alt in meters, and dwell in seconds.
    Raises: ValueError for an invalid mission object or items list.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("mission"), dict):
        raise ValueError("Plan must contain a mission object")
    mission = plan.get("mission", {})
    issues = []
    waypoints = []
    takeoffs = []
    home = mission.get("plannedHomePosition")
    if not isinstance(home, list) or len(home) < 2 or not coordinates(*home[:2]):
        home = None
        issues.append(
            "plannedHomePosition latitude/longitude is unspecified or invalid"
        )
    items = mission.get("items", [])
    if not isinstance(items, list):
        raise ValueError("mission.items must be a list")
    terminal = False
    for order, item in enumerate(items, 1):
        if not isinstance(item, dict) or item.get("type") != "SimpleItem":
            issues.append(
                f"Item {order}: ComplexItem or unknown item pattern is unsupported"
            )
            continue
        command = item.get("command")
        if terminal:
            issues.append(f"Item {order}: behavior after RTL/land is unsupported")
        if command == 16:
            waypoint = parse_waypoint(item, order, issues)
            if waypoint is not None:
                waypoints.append(waypoint)
        elif command == 22:
            # Takeoff params[0] is pitch, NOT hold time. No takeoff-altitude check.
            takeoffs.append(
                dict(order=order, frame=item.get("frame"), params=item.get("params"))
            )
            if len(takeoffs) > 1 or waypoints:
                issues.append(
                    f"Item {order}: multiple or mid-mission takeoffs are unsupported"
                )
            if item.get("frame") not in (0, 3):
                issues.append(f"Item {order}: unsupported takeoff altitude frame")
        elif command in (20, 21):
            terminal = True  # RTL/land define no selected waypoint requirement
        else:
            issues.append(f"Item {order}: unsupported command {command}")
    if not waypoints:
        issues.append("No command-16 waypoint requirements found")
    return dict(home=home, waypoints=waypoints, takeoffs=takeoffs, issues=issues)


def load_requirement(path):
    """Read a JSON .plan file and extract mission requirements.

    Args: path (str | pathlib.Path), path to the plan.
    Returns: dict from parse_mission().
    Raises: OSError for an unreadable file; ValueError for invalid JSON/structure.
    """
    with Path(path).open(encoding="utf-8-sig") as stream:
        return parse_mission(json.load(stream))


def load_log(path):
    """Parse a binary .ulg once with pyulog, closing its stream even on error.

    Args: path (str | pathlib.Path), flight log path.
    Returns: pyulog.ULog containing loaded datasets and metadata.
    Raises: ImportError if pyulog is unavailable; ValueError on read/parse errors.
    """
    from pyulog import ULog

    try:
        # Own the stream so parser errors cannot leave a file handle open.
        with Path(path).open("rb") as stream:
            return ULog(stream)
    except Exception as error:
        # pyulog versions use several parser exception types for corrupt files.
        raise ValueError(f"Cannot parse ULog: {error}") from error


def topic_rows(ulog, name):
    """Convert a topic into rows, preserving invalid measurements.

    Args: ulog (pyulog.ULog), loaded log; name (str), exact topic name.
    Returns: list[dict] with original fields and t in seconds since system start;
        empty if absent. NumPy scalars become Python values.
    Raises: ValueError for multiple instances, bad lengths, or invalid timestamps.
    """
    datasets = [d for d in ulog.data_list if d.name == name]
    if len(datasets) > 1:
        raise ValueError(f"Multiple instances of {name}; source is ambiguous")
    if not datasets:
        return []
    data = datasets[0].data
    timestamps = data.get("timestamp", [])
    if any(len(values) != len(timestamps) for values in data.values()):
        raise ValueError(f"Mismatched field lengths in {name}")
    rows = []
    previous = -1
    for i, timestamp in enumerate(timestamps):
        timestamp = float(timestamp)
        if not math.isfinite(timestamp) or timestamp <= previous or timestamp <= 0:
            raise ValueError(f"Invalid or non-increasing timestamps in {name}")
        previous = timestamp
        row = {}
        for key, values in data.items():
            value = values[i]
            if hasattr(value, "item"):
                value = value.item()  # Convert NumPy values to Python values.
            row[key] = value
        row["t"] = timestamp / 1e6
        rows.append(row)
    return rows


def position_valid(row, altitude=True):
    """Check coordinates, optional altitude, and any available validity flags.

    Args: row (dict), lat/lon in degrees, alt in meters MSL, optional validity flags;
        altitude (bool, optional), whether to check altitude; defaults to True.
    Returns: bool. Older schemas may omit flags, but required values must be finite.
    """
    if not coordinates(row.get("lat"), row.get("lon")):
        return False
    if row.get("lat_lon_valid", True) != 1:
        return False
    if altitude:
        return finite(row.get("alt")) and row.get("alt_valid", True) == 1
    return True


def extract_telemetry(ulog):
    """Choose one position source and extract supporting topic rows.

    Args: ulog (pyulog.ULog), already loaded log.
    Returns: dict with positions, source label, land/home/armed/mission rows,
        and corrupt/dropouts flags. Prefer valid ground truth, otherwise estimated
        position; never switch the source during verification.
    Raises: ValueError if topic_rows() rejects a topic.
    """
    groundtruth = topic_rows(ulog, "vehicle_global_position_groundtruth")
    if any(position_valid(row) for row in groundtruth):
        positions, source = (
            groundtruth,
            "vehicle_global_position_groundtruth (simulator ground truth)",
        )
    else:
        positions = topic_rows(ulog, "vehicle_global_position")
        source = "vehicle_global_position (ESTIMATED telemetry)"
    return dict(
        positions=positions,
        source=source,
        land=topic_rows(ulog, "vehicle_land_detected"),
        home=topic_rows(ulog, "home_position"),
        armed=topic_rows(ulog, "actuator_armed"),
        mission=topic_rows(ulog, "mission_result"),
        corrupt=bool(getattr(ulog, "file_corruption", False)),
        dropouts=bool(getattr(ulog, "dropouts", [])),
    )


def result(status, reason):
    """Create a verdict with its explanation and evidence.

    Args: status (str), PASS/FAIL/INCONCLUSIVE; reason (str), explanation.
    Returns: dict[str, str] with status and reason.
    """
    return dict(status=status, reason=reason)


# Establish which flight the observations belong to


def flight_window(telemetry, max_gap):
    """Identify one flight and reject ambiguous or multiple executions.

    Args: telemetry (dict), extracted land/armed/mission rows;
        max_gap (int | float), maximum land-detector gap in seconds.
    Returns: tuple of takeoff time (float | None), end time (float | None), and
        ambiguity reason (str | None). Times are seconds since system start;
        an unknown end is None, while ambiguity returns (None, None, reason).
    """
    land = telemetry["land"]
    if not land or any(row.get("landed") not in (0, 1) for row in land):
        return None, None, "Missing/invalid vehicle_land_detected evidence"
    if land[0]["landed"] != 1:
        return (
            None,
            None,
            "Recording begins airborne; launch or earlier flight is unknown",
        )
    takeoff_times = []
    has_gap = False
    for previous, current in zip(land, land[1:], strict=False):
        if previous["landed"] == 1 and current["landed"] == 0:
            takeoff_times.append(current["t"])
        if current["t"] - previous["t"] > max_gap:
            has_gap = True
    if len(takeoff_times) != 1:
        return None, None, "No unique takeoff: missing takeoff or multiple flights"
    if has_gap:
        return None, None, "Land-detector gaps make the number of flights ambiguous"
    start = takeoff_times[0]
    ends = [row["t"] for row in land if row["t"] > start and row["landed"] == 1]
    armed = telemetry["armed"]
    if any(row.get("armed") not in (0, 1) for row in armed):
        return None, None, "Invalid arming evidence"
    arming_count = 0
    disarms = []
    for previous, current in zip(armed, armed[1:], strict=False):
        if previous["armed"] == 0 and current["armed"] == 1:
            arming_count += 1
        if previous["armed"] == 1 and current["armed"] == 0 and current["t"] > start:
            disarms.append(current["t"])
    if arming_count > 1:
        return None, None, "Multiple arming sessions: mission execution is ambiguous"
    end = min(ends + disarms, default=None)
    active = [r for r in telemetry["mission"] if start <= r["t"] <= (end or math.inf)]
    ids = {r["mission_id"] for r in active if r.get("valid") == 1 and "mission_id" in r}
    sequences = [
        r["seq_current"] for r in active if r.get("valid") == 1 and "seq_current" in r
    ]
    if len(ids) > 1 or any(
        b < a for a, b in zip(sequences, sequences[1:], strict=False)
    ):
        return None, None, "Mission change/restart detected; execution is ambiguous"
    return start, end, None


# Check launch location, waypoint altitude, and consecutive dwell


def check_launch(mission, positions, start, tolerance, max_gap):
    """Compare the last pre-takeoff position with planned home.

    Args: mission (dict), parsed home coordinates;
        positions (list[dict]), time-ordered rows;
        start (float | None), takeoff time in seconds since system start;
        tolerance (int | float), allowed horizontal error in meters;
        max_gap (int | float), maximum pre-takeoff position age in seconds.
    Returns: dict[str, str] with status and evidence. Missing/stale/invalid data
        gives INCONCLUSIVE.
    """
    if mission["home"] is None or start is None:
        return result(
            INCONCLUSIVE, "Expected launch location or unique takeoff is unavailable"
        )
    preceding = [row for row in positions if row["t"] < start]
    row = preceding[-1] if preceding else None
    if (
        row is None
        or not position_valid(row, altitude=False)
        or start - row["t"] > max_gap
    ):
        return result(
            INCONCLUSIVE,
            "No sufficiently recent valid position immediately before takeoff",
        )
    error = distance_m(row["lat"], row["lon"], *mission["home"][:2])
    return result(
        PASS if error <= tolerance else FAIL,
        f"distance={error:.2f} m, tolerance={tolerance:g} m, "
        f"t={row['t']:.3f} s; takeoff={start:.3f} s",
    )


def home_altitude(homes, timestamp):
    """Look up the latest home altitude at or before a position time.

    Args: homes (list[dict]), time-ordered home states with alt and valid_alt;
        timestamp (int | float), seconds since system start.
    Returns: int | float meters MSL, or None if the latest applicable home state
        is missing/invalid. Never use future updates.
    """
    index = bisect_right([row["t"] for row in homes], timestamp) - 1
    if index < 0:
        return None
    row = homes[index]
    return (
        row.get("alt") if row.get("valid_alt") == 1 and finite(row.get("alt")) else None
    )


def target_altitude(wp, homes, timestamp):
    """Convert a supported waypoint altitude to meters MSL.

    Args: wp (dict), validated alt in meters and frame 0 (MSL) or 3 (relative home);
        homes (list[dict]), time-ordered logged home states;
        timestamp (int | float), position time in seconds since system start.
    Returns: int | float MSL target, or None if frame 3 lacks valid logged home.
    """
    if wp["frame"] == 0:
        return wp["alt"]
    home = home_altitude(homes, timestamp)
    return None if home is None else home + wp["alt"]


def check_waypoint(
    wp, samples, homes, horizontal, vertical, max_gap, complete, data_ok
):
    """Search forward for arrival, simultaneous altitude match, and dwell.

    Args: wp (dict), validated lat/lon (degrees), alt (meters), frame, dwell (seconds);
        samples (list[dict]), remaining positions in time order;
        homes (list[dict]), home states in time order;
        horizontal, vertical (int | float), allowed position/altitude errors in meters;
        max_gap (int | float), maximum gap counted toward dwell in seconds;
        complete (bool), whether landing/disarming establishes flight end;
        data_ok (bool), whether coverage and integrity support failure decisions.
    Returns: (dict of arrival/altitude/dwell results, int | None last consumed index).
        Index is None if no visit qualifies. Invalid data, gaps, departures, and
        changed altitude references reset dwell.
    """
    arrival = altitude = None
    best_horizontal = best_vertical = math.inf
    hold_start = previous_time = previous_target = None
    achieved_dwell = 0.0
    uncertain = not data_ok
    for index, row in enumerate(samples):
        timestamp = row["t"]
        if not position_valid(row, altitude=False):
            uncertain = True
            hold_start = previous_time = None
            continue
        horizontal_error = distance_m(row["lat"], row["lon"], wp["lat"], wp["lon"])
        best_horizontal = min(best_horizontal, horizontal_error)
        within_horizontal = horizontal_error <= horizontal
        if within_horizontal and arrival is None:
            arrival = result(
                PASS, f"t={timestamp:.3f} s, horizontal error={horizontal_error:.2f} m"
            )

        target = target_altitude(wp, homes, timestamp)
        if not position_valid(row) or target is None:
            uncertain = True
            hold_start = previous_time = None
            continue
        vertical_error = abs(row["alt"] - target)
        if within_horizontal:
            best_vertical = min(best_vertical, vertical_error)
        inside = within_horizontal and vertical_error <= vertical

        # A gap or changed home reference breaks continuous dwell evidence.
        if previous_time is not None and (
            timestamp - previous_time > max_gap or target != previous_target
        ):
            hold_start = None
            uncertain = True
        if inside:
            if altitude is None:
                altitude = result(
                    PASS,
                    f"t={timestamp:.3f} s, vertical error={vertical_error:.2f} m, "
                    f"target={target:.2f} m MSL",
                )
            if hold_start is None:
                hold_start = timestamp
            current_dwell = timestamp - hold_start
            achieved_dwell = max(achieved_dwell, current_dwell)
            if current_dwell >= wp["dwell"]:
                dwell = result(
                    PASS,
                    f"achieved={current_dwell:.3f} s, required={wp['dwell']:g} s, "
                    f"t={hold_start:.3f}..{timestamp:.3f} s",
                )
                return dict(arrival=arrival, altitude=altitude, dwell=dwell), index
        else:
            hold_start = None
        previous_time = timestamp
        previous_target = target

    # An unobserved requirement is a failure only with complete, valid evidence.
    status = FAIL if complete and not uncertain else INCONCLUSIVE
    why = (
        "ended flight with valid coverage"
        if status == FAIL
        else "incomplete recording, invalid data, gap, or missing altitude reference"
    )
    arrival = arrival or result(
        status, f"No ordered arrival; nearest={best_horizontal:.2f} m; {why}"
    )
    altitude = altitude or result(
        status,
        "No simultaneous horizontal/altitude match; "
        f"best vertical error inside horizontal region={best_vertical:.2f} m; {why}",
    )
    if wp["dwell"] == 0:
        dwell = result(PASS, "Zero dwell: no hold required")
    else:
        dwell = result(
            status,
            f"achieved={achieved_dwell:.3f} s, required={wp['dwell']:g} s; {why}",
        )
    return dict(arrival=arrival, altitude=altitude, dwell=dwell), None


def unknown_waypoint(reason):
    """Mark all three checks for an unresolved waypoint INCONCLUSIVE.

    Args: reason (str), shared explanation.
    Returns: dict containing arrival, altitude, and dwell result dictionaries.
    """
    return {
        name: result(INCONCLUSIVE, reason) for name in ("arrival", "altitude", "dwell")
    }


def has_position_coverage(samples, start, end, max_gap):
    """Check that position samples cover the flight without excessive gaps.

    Args: samples (list[dict]), flight positions in time order;
        start, end (float | None), flight bounds in seconds since system start
        (start must be known when samples are nonempty and end is known);
        max_gap (int | float), largest acceptable gap in seconds.
    Returns: bool, whether both boundaries and every sample gap are covered.
    """
    if not samples or end is None:
        return False
    if samples[0]["t"] - start > max_gap:
        return False
    if end - samples[-1]["t"] > max_gap:
        return False
    for previous, current in zip(samples, samples[1:], strict=False):
        if current["t"] - previous["t"] > max_gap:
            return False
    return True


def find_waypoint_exit(waypoint, samples, cursor, homes, horizontal, vertical):
    """Find an exit before allowing a new visit to a repeated location.

    Args: waypoint (dict), previous completed requirement;
        samples (list[dict]), flight positions; cursor (int), first search index;
        homes (list[dict]), time-ordered home states;
        horizontal, vertical (int | float), position/altitude tolerances in meters.
    Returns: int index of the first valid sample outside either tolerance, or None.
    """
    for index in range(cursor, len(samples)):
        row = samples[index]
        target = target_altitude(waypoint, homes, row["t"])
        if not position_valid(row) or target is None:
            continue
        horizontal_error = distance_m(
            row["lat"], row["lon"], waypoint["lat"], waypoint["lon"]
        )
        vertical_error = abs(row["alt"] - target)
        if horizontal_error > horizontal or vertical_error > vertical:
            return index
    return None


# Coordinate the checks in flight order


def verify(
    mission,
    telemetry,
    launch_tolerance,
    horizontal_tolerance,
    altitude_tolerance,
    max_gap=DEFAULT_MAX_GAP,
):
    """Run the four selected requirements and combine their verdicts.

    Args: mission (dict), parsed requirements;
        telemetry (dict), extracted observations;
        launch_tolerance, horizontal_tolerance, altitude_tolerance (int | float),
        allowed launch/waypoint/altitude errors in meters;
        max_gap (int | float, optional), sample gap/launch age in seconds; default 1.
    Returns: dict with source, launch, ordered waypoints, issues, and overall.
        Verdict priority is FAIL, then INCONCLUSIVE, then PASS.
    Raises: ValueError for negative/nonfinite tolerances or a
        nonpositive/nonfinite gap.
    """
    for value in (launch_tolerance, horizontal_tolerance, altitude_tolerance, max_gap):
        if not finite(value) or value < 0:
            raise ValueError("Tolerances must be finite and nonnegative")
    if max_gap == 0:
        raise ValueError("Maximum sample gap must be positive")
    # 1. Establish the flight and check its launch location.
    start, end, ambiguity = flight_window(telemetry, max_gap)
    positions = telemetry["positions"]
    launch = check_launch(mission, positions, start, launch_tolerance, max_gap)
    # 2. Record limitations that prevent a complete decision.
    issues = list(mission["issues"])
    if ambiguity:
        issues.append(ambiguity)
    if end is None:
        issues.append(
            "Flight end not established by landing/disarming; "
            "recording may be interrupted"
        )
    if telemetry["corrupt"] or telemetry["dropouts"]:
        issues.append(
            "ULog corruption/dropouts: missing observations may hide "
            "violations or visits"
        )
    flight = [
        row
        for row in positions
        if start is not None and start <= row["t"] <= (end or math.inf)
    ]
    coverage = has_position_coverage(flight, start, end, max_gap)
    if not coverage:
        issues.append(
            "Position coverage is missing, interrupted, or has a critical gap"
        )
    data_ok = (
        coverage
        and not telemetry["corrupt"]
        and not telemetry["dropouts"]
        and all(position_valid(row) for row in flight)
    )
    # 3. Consume each waypoint's qualifying visit before checking the next.
    reports = []
    cursor = 0
    previous_wp = None
    blocked = bool(
        mission["issues"] or ambiguity or telemetry["corrupt"] or telemetry["dropouts"]
    )
    for wp in mission["waypoints"]:
        if blocked:
            reports.append(
                unknown_waypoint(
                    "Unsupported/ambiguous plan or previous ordered "
                    "requirement unresolved"
                )
            )
            continue
        # Duplicate locations need a distinct visit, not another slice of the same hold.
        if previous_wp and (wp["lat"], wp["lon"]) == (
            previous_wp["lat"],
            previous_wp["lon"],
        ):
            exit_index = find_waypoint_exit(
                previous_wp,
                flight,
                cursor,
                telemetry["home"],
                horizontal_tolerance,
                altitude_tolerance,
            )
            if exit_index is None:
                reports.append(
                    unknown_waypoint("Repeated location has no distinct observed visit")
                )
                blocked = True
                continue
            cursor = exit_index
        checks, consumed = check_waypoint(
            wp,
            flight[cursor:],
            telemetry["home"],
            horizontal_tolerance,
            altitude_tolerance,
            max_gap,
            end is not None,
            data_ok,
        )
        reports.append(checks)
        if consumed is None:
            blocked = True
        else:
            cursor += consumed + 1
        previous_wp = wp
    # 4. An established failure takes precedence over incomplete evidence.
    statuses = [launch["status"]]
    for checks in reports:
        for check in checks.values():
            statuses.append(check["status"])
    if FAIL in statuses:
        overall = FAIL
    elif issues or INCONCLUSIVE in statuses:
        overall = INCONCLUSIVE
    else:
        overall = PASS
    return dict(
        source=telemetry["source"],
        launch=launch,
        waypoints=reports,
        issues=issues,
        overall=overall,
    )


# Display results and collect command-line input


def print_requirements(mission):
    """Display requirements, units, frames, issues, and the launch assumption.

    Args: mission (dict), parsed home/takeoffs/waypoints/issues.
    Returns: None; writes to standard output.
    """
    print(
        "Assumption: plannedHomePosition latitude/longitude is the expected "
        "launch location."
    )
    print(
        f"Planned home: {mission['home']} (planned altitude is not used for conversion)"
    )
    for takeoff in mission["takeoffs"]:
        print(
            f"Item {takeoff['order']}: takeoff (command 22), "
            f"frame={takeoff['frame']}; no dwell extracted"
        )
    for i, wp in enumerate(mission["waypoints"], 1):
        print(
            f"Waypoint {i} (item {wp['order']}): lat={wp['lat']}, lon={wp['lon']}, "
            f"alt={wp['alt']} m, frame={wp['frame']}, dwell={wp['dwell']} s"
        )
    for issue in mission["issues"]:
        print(f"Unsupported/unspecified: {issue}")


def print_overall(status, reason=""):
    """Print a colored verdict, then reset the terminal color.

    Args: status (str), PASS (green), FAIL (red), or INCONCLUSIVE (yellow);
        reason (str, optional), appended text including any separator; defaults to ''.
    Returns: None; writes ANSI-colored output.
    """
    colors = {PASS: "\033[32m", FAIL: "\033[31m", INCONCLUSIVE: "\033[33m"}
    print(f"{colors[status]}Overall: {status}\033[0m{reason}")


def print_report(report):
    """Display source, check evidence, overall verdict, and verification scope.

    Args: report (dict), returned by verify().
    Returns: None; writes the terminal report.
    """
    print("\nMission verification for the four selected requirements.")
    print(f"Position source: {report['source']}")
    print(f"Launch: {report['launch']['status']} - {report['launch']['reason']}")
    for i, checks in enumerate(report["waypoints"], 1):
        for name, check in checks.items():
            print(f"Waypoint {i} {name}: {check['status']} - {check['reason']}")
    for issue in report["issues"]:
        print(f"INCONCLUSIVE evidence: {issue}")
    print_overall(report["overall"])


def prompt_number(label, default=None, positive=False):
    """Prompt until input is finite and in the allowed range.

    Args: label (str), prompt including units;
        default (int | float | None, optional), empty-input value; defaults to None;
        positive (bool, optional), require greater than zero if True, otherwise
        allow zero; defaults to False.
    Returns: int | float accepted value; prints prompts and validation feedback.
    """
    prompt = label
    if default is not None:
        prompt += f" [{default:g}]"
    while True:
        text = input(prompt + ": ").strip()
        try:
            if not text and default is not None:
                value = default
            else:
                value = float(text)
            if finite(value) and (value > 0 if positive else value >= 0):
                return value
        except ValueError:
            pass
        print(
            "Enter a finite positive number."
            if positive
            else "Enter a finite nonnegative number."
        )


def prompt_path(label):
    """Read a path, strip surrounding quotes, and expand the home shortcut.

    Args: label (str), prompt identifying the file.
    Returns: pathlib.Path with spaces preserved; does not check existence.
        Writes the prompt to standard output.
    """
    return Path(input(label + ": ").strip().strip("\"'")).expanduser()


def main():
    """Prompt for inputs, run verification, and display requirements and results.

    Args: None; reads --max-gap from the CLI and paths and tolerances from
        standard input. Dwell requirements come directly from the plan.
    Returns: int exit code: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, or 3 if verification
        cannot run (bad arguments, unreadable inputs, or invalid/unsupported plan).
        --help prints usage and returns 0 without running verification.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-gap",
        type=float,
        default=DEFAULT_MAX_GAP,
        help="maximum position gap and launch-position age, seconds (default: 1)",
    )
    try:
        args = parser.parse_args()
        if not finite(args.max_gap) or args.max_gap <= 0:
            parser.error("--max-gap must be finite and positive")
    except SystemExit as error:
        # argparse uses 2 for argument errors; reserve 2 for evidence uncertainty.
        return 0 if error.code == 0 else 3
    try:
        plan_path = prompt_path("QGroundControl .plan file path")
        log_path = prompt_path("PX4 .ulg log file path")
        mission = load_requirement(plan_path)
        print_requirements(mission)
        if mission["issues"]:
            print(
                "Couldn't run: invalid or unsupported mission plan (see issues above)."
            )
            return 3
        launch = prompt_number("Launch tolerance (m)")
        horizontal = prompt_number("Waypoint horizontal tolerance (m)")
        vertical = prompt_number("Altitude tolerance (m)")
        print(
            f"Tolerances: launch={launch:g} m, horizontal={horizontal:g} m, "
            f"vertical={vertical:g} m; maximum gap={args.max_gap:g} s"
        )
        ulog = load_log(log_path)
        try:
            telemetry = extract_telemetry(ulog)
        except ValueError as error:
            # The file was read, but ambiguous/invalid telemetry prevents a verdict.
            print_overall(INCONCLUSIVE, f" - invalid or ambiguous telemetry: {error}")
            return 2
        report = verify(mission, telemetry, launch, horizontal, vertical, args.max_gap)
        print_report(report)
        return {PASS: 0, FAIL: 1, INCONCLUSIVE: 2}[report["overall"]]
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ImportError,
        EOFError,
    ) as error:
        print(f"Couldn't run: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
