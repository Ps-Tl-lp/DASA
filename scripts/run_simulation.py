"""Run an accepted QGC plan in a fresh local PX4 SITL instance (Linux/WSL)."""

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from px4_flyer import Flyer, RunError


def atomic_json(path, value):
    temporary = path.with_suffix(".partial")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def resolve(config, value):
    if isinstance(value, str):
        result = config
        for part in value.split("."):
            result = result[part]
        return result
    return value


def plan_items(plan):
    if plan.get("fileType") != "Plan":
        raise ValueError("expected QGroundControl Plan")
    if plan.get("rallyPoints", {}).get("points"):
        raise ValueError("rally points are unsupported")
    fence = plan.get("geoFence", {})
    if fence.get("circles") or fence.get("polygons"):
        raise ValueError(
            "PX4 geofence upload is unsupported; use mission postconditions"
        )
    items = plan["mission"]["items"]
    if not items:
        raise ValueError("cannot fly an empty plan")
    for item in items:
        if item.get("type") != "SimpleItem" or item.get("frame") not in (0, 2, 3):
            raise ValueError("unsupported mission item type/frame")
        if (
            item.get("command") not in (16, 20, 22, 203)
            or item.get("autoContinue") is not True
        ):
            raise ValueError("unsupported command or non-continuing item")
        params = item["params"]
        if len(params) != 7:
            raise ValueError("expected seven mission parameters")
        for i, value in enumerate(params):
            if value is None and i == 3:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError("invalid mission parameter")
    return items


def stop_process(process):
    # The group can outlive its PX4 parent (which starts Gazebo).
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            continue
        if sig == signal.SIGINT:
            # Reap remaining owned children as well.
            continue
        return


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--start", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--px4", required=True, type=Path, help="built PX4 source checkout"
    )
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--output", required=True, type=Path, help="new directory, never overwritten"
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--setup-timeout", type=float, default=60)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    folder = args.output.resolve()
    record = {
        "mission_id": args.mission_id,
        "run_id": args.run_id,
        "plan": "mission.plan",
        "run_status": "inconclusive",
        "reason": "sim_setup",
        "source": "simulator",
        "log": None,
        "recording": "gz_pose.jsonl",
        "record": {},
    }
    atomic_json(folder / "run.json", record)
    processes, handles = [], []
    temporary = None
    link = None

    def event(kind, **fields):
        with (folder / "harness-events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"event": kind, "wall_monotonic_s": time.monotonic(), **fields}
                )
                + "\n"
            )

    def launch(command, filename, **kwargs):
        stream = (folder / filename).open("w", encoding="utf-8")
        handles.append(stream)
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            **kwargs,
        )
        processes.append(process)
        return process

    try:
        import yaml

        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        sim = config["sim"]
        timeout = float(sim["flight_timeout_s"])
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or not math.isfinite(args.setup_timeout)
            or args.setup_timeout <= 0
        ):
            raise ValueError("timeouts must be positive finite wall-clock seconds")
        px4 = args.px4.resolve()
        build = subprocess.check_output(
            ["git", "-C", str(px4), "rev-parse", "HEAD"], text=True
        ).strip()
        record["record"] = {
            "px4_commit": build,
            "simulator": sim["simulator"],
            "speed": sim["speed_factor"],
        }
        if not build.startswith(str(sim["px4_build"])):
            raise ValueError(
                f"PX4 {build[:10]} differs from configured baseline {sim['px4_build']}"
            )
        from pymavlink import mavutil

        if sys.platform != "linux":
            raise ValueError("run inside Linux/WSL with Gazebo Harmonic")
        items = plan_items(json.loads(args.plan.read_text(encoding="utf-8")))
        home = json.loads(args.plan.read_text(encoding="utf-8"))["mission"][
            "plannedHomePosition"
        ]
        expected_home = [config["base_lat_lon"][k] for k in ("lat", "lon", "alt")]
        if len(home) != 3 or any(
            abs(a - b) > 1e-7 for a, b in zip(home, expected_home, strict=True)
        ):
            raise ValueError("plan home differs from configured simulator home")
        agent = ET.parse(args.start).getroot().find(".//agent")
        if agent is None:
            raise ValueError("start state has no agent")
        vehicle = agent.get("vehicle_type")
        if vehicle is None:
            field = agent.find("vehicle_type")
            vehicle = field.get("value") if field is not None else None
        selected = config["vehicle_types"][vehicle]
        model = selected["sim_model"]
        settings = {k: resolve(config, v) for k, v in config["px4_setup"].items()}
        settings.update(selected.get("px4_setup", {}))
        record["record"].update(model=model, parameters=settings)
        if args.seed is not None:
            record["record"]["seed"] = args.seed
        for src, name in (
            (args.plan, "mission.plan"),
            (args.start, "start.xml"),
            (args.config, "px4.yaml"),
        ):
            shutil.copy2(src, folder / name)
        env = os.environ.copy()
        env.update(
            GZ_PARTITION="hydra_" + uuid.uuid4().hex,
            PX4_SIM_MODEL=model,
            PX4_GZ_WORLD=sim["world"],
            PX4_SIM_SPEED_FACTOR=str(sim["speed_factor"]),
        )
        # Ignore inherited attachment settings; this attempt owns a new simulator.
        for key in ("PX4_GZ_MODEL_NAME", "PX4_GZ_STANDALONE"):
            env.pop(key, None)
        if sim["headless"]:
            env["HEADLESS"] = "1"
        else:
            env.pop("HEADLESS", None)
        for key, value in zip(("LAT", "LON", "ALT"), expected_home, strict=True):
            env["PX4_HOME_" + key] = str(value)
        env["PX4_GZ_MODELS"] = str(px4 / "Tools/simulation/gz/models")
        env["PX4_GZ_WORLDS"] = str(px4 / "Tools/simulation/gz/worlds")
        env["GZ_SIM_RESOURCE_PATH"] = env["PX4_GZ_MODELS"] + ":" + env["PX4_GZ_WORLDS"]
        env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = str(
            px4 / "build/px4_sitl_default/src/modules/simulation/gz_plugins"
        )
        env["GZ_SIM_SERVER_CONFIG_PATH"] = str(
            px4 / "src/modules/simulation/gz_bridge/server.config"
        )
        recorder = launch(
            [
                sys.executable,
                str(Path(__file__).with_name("gz_recorder.py")),
                "--topic",
                sim["pose_topic"],
                "--model",
                model.removeprefix("gz_") + "_0",
                "--output",
                str(folder / "gz_pose.jsonl"),
                "--ready",
                str(folder / ".recorder-ready"),
            ],
            "recorder-output.log",
            env=env,
        )
        deadline = time.monotonic() + args.setup_timeout
        while not (folder / ".recorder-ready").exists():
            if recorder.poll() is not None or time.monotonic() >= deadline:
                raise RunError(
                    "sim_setup", "recorder could not subscribe; see recorder-output.log"
                )
            time.sleep(0.05)
        temporary = Path(tempfile.mkdtemp(prefix="hydra-sitl-"))
        (temporary / "etc").symlink_to(
            px4 / "build/px4_sitl_default/etc", target_is_directory=True
        )
        # Bind before PX4 launches so every attempt owns the simulator API port.
        link = mavutil.mavlink_connection("udpin:127.0.0.1:14540", source_system=245)
        simulation = launch(
            [str(px4 / "build/px4_sitl_default/bin/px4"), "-d", "-w", str(temporary)],
            "px4-gazebo-output.log",
            cwd=temporary,
            env=env,
        )

        def health():
            if simulation.poll() is not None:
                raise RunError("sim_died", "PX4 simulation process exited")
            if recorder.poll() is not None:
                raise RunError("sim_setup", "recorder exited during run")

        flyer = Flyer(link, event, health, args.setup_timeout)
        actual = flyer.fly(items, settings, timeout)
        record["record"]["parameters"] = actual
        record.update(run_status="completed", reason=None)
        # Let the logger close after disarm while the recorder continues.
        until = time.monotonic() + 3
        while time.monotonic() < until:
            health()
            time.sleep(0.1)
    except KeyboardInterrupt:
        event("interrupted")
        record.update(run_status="inconclusive", reason="sim_died")
    except Exception as exc:
        record.update(
            run_status="inconclusive", reason=getattr(exc, "reason", "sim_setup")
        )
        event("error", reason=record["reason"], detail=str(exc))
        print(str(exc), file=sys.stderr)
    finally:
        # PX4/Gazebo stop first; the recorder remains subscribed through final samples.
        for process in reversed(processes):
            stop_process(process)
        if link is not None:
            link.close()
        for handle in handles:
            handle.close()
        if temporary is not None:
            logs = list(temporary.rglob("*.ulg"))
            if len(logs) == 1:
                shutil.copy2(logs[0], folder / "flight.ulg")
                record["log"] = "flight.ulg"
            elif record["run_status"] == "completed":
                record.update(
                    run_status="inconclusive",
                    reason="no_log" if not logs else "several_logs",
                )
            # Retain working files for diagnosis; never delete evidence after failure.
            event("working_directory", path=str(temporary), logs=[str(p) for p in logs])
        atomic_json(folder / "run.json", record)
    print(folder / "run.json")
    return 0 if record["run_status"] == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
