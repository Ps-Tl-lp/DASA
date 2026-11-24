"""Run one mission through the whole pipeline: generate, plan, fly, read, verify.

    python scripts/run_mission.py --template XML --settings YAML --out DIR [--seed N]
    python scripts/run_mission.py --mission DIR
    ... [--px4 PX4_CHECKOUT [--run-id ID] | --run RUN_FOLDER] [--config PATH]
    python scripts/run_mission.py --run RUN_FOLDER        (a run, from what it kept)

1. The mission folder: --template and --settings generate a new one in --out
   (start.xml, goal.xml and a copy of the settings), or --mission names one.
2. The plan step writes mission.plan beside them. A mission.plan already there must
   be the one the plan step builds.
3. The flight: --px4 flies the plan with the harness (Linux, WSL or macOS, with
   Gazebo Harmonic) into the run folder DIR/RUN_ID, which keeps the plan, the
   states, the settings (settings.yaml) and the config (px4.yaml) with the run; --run
   names a run that was already flown. With neither, it stops after the plan.
   A run named with --run must be this mission's: the same mission id, the plan it
   flew the same as the mission's, and any states and settings it kept the same. It
   is read and verified with the px4.yaml it kept; a --config that differs is refused.
4. The log reader writes the run's readings.json. A run with no flight log still gets
   one, empty and saying why, so its verdict is INCONCLUSIVE.
5. The verifier writes the run's verdict.json, from the copies the run folder keeps
   if it has them, and the verdict is printed. A run already read or verified is left
   as it is.

Each step is the piece's own code, called as it is. Exit status: 0 when a verdict was
written, 1 when a step stopped with an error, 2 when no flight was given.
"""

import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # the plan step, log reader and verifier packages
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the other scripts

from generate_mission import GeneratorError, generate, write_outputs  # noqa: E402

from log_reader.readings import ReaderError, read_run, readings_text  # noqa: E402
from plan_step import PlanError, build_plan, plan_text  # noqa: E402
from plan_step.config import load_config  # noqa: E402
from verifier.cli import main as verify  # noqa: E402

DEFAULT_CONFIG = ROOT / "platform_configs" / "px4.yaml"
# What the harness calls the mission settings it keeps with a run.
KEPT_SETTINGS = "settings.yaml"


class StepError(Exception):
    """A step that stopped. The message says which step and why."""


def make_mission(template, settings, out, config, seed):
    """Generate a mission folder in `out`, which must not exist yet."""
    if out.exists():
        raise StepError(f"generate: {out} already exists; name a new folder")
    try:
        result = generate(template, settings, config, seed)
        out.mkdir(parents=True)
        write_outputs(result, out, (template, settings, config))
    except (GeneratorError, OSError) as error:
        raise StepError(f"generate: {error}") from error
    # The plan step and the verifier read the hold from the settings, kept beside
    # the two states. A byte-for-byte copy, so nothing is lost or reworded.
    shutil.copy2(settings, out / settings.name)
    print(f"generate: {out} (seed {seed})")


def plan(mission, config_path, write=True):
    """The plan step's plan for the mission, as text. Written to mission.plan when
    there isn't one yet, unless `write` is false: a replay writes nothing but the
    run's readings and verdict."""
    try:
        config = load_config(config_path)
        text = plan_text(build_plan(mission, config, settings=settings_path(mission)))
    except PlanError as error:
        raise StepError(f"plan: no plan: {error}") from error
    path = mission / "mission.plan"
    if path.exists() and path.read_text() != text:
        raise StepError(
            f"plan: {path} differs from the plan the plan step builds; "
            "remove it to write it again"
        )
    if not path.exists() and write:
        path.write_text(text)
    print(f"plan: {path}" if path.exists() else "plan: built to compare (not written)")
    return path, text


def fly(mission, plan_path, config_path, px4, run_id, seed):
    """Fly with the harness. Its own checks refuse anything but Linux, WSL or macOS
    with Gazebo Harmonic."""
    from run_simulation import main as run_harness  # imported only to fly

    settings_file = settings_path(mission)
    settings = yaml.safe_load(settings_file.read_text()) or {}
    run = mission / run_id
    args = [
        "--plan", str(plan_path),
        "--start", str(mission / "start.xml"),
        "--goal", str(mission / "goal.xml"),
        "--settings", str(settings_file),
        "--config", str(config_path),
        "--px4", str(px4),
        "--mission-id", str(settings.get("mission_id", mission.name)),
        "--run-id", run_id,
        "--output", str(run),
    ]  # fmt: skip
    if seed is not None:
        args += ["--seed", str(seed)]
    status = run_harness(args)
    print(f"fly: {run} (harness exit {status})")
    return run


def match_run(mission, run, plan):
    """A run replayed against a mission must be that mission's own run. `plan` is the
    text of the plan the plan step builds for the mission, held in memory."""
    try:
        record = json.loads((run / "run.json").read_text())
    except (OSError, ValueError) as error:
        raise StepError(f"run: can't read {run / 'run.json'}: {error}") from error
    ours = yaml.safe_load(settings_path(mission).read_text()) or {}
    if record.get("mission_id") != ours.get("mission_id"):
        raise StepError(
            f"run: {run} is a run of mission {record.get('mission_id')!r}, "
            f"not {ours.get('mission_id')!r}"
        )
    flown = run / str(record.get("plan"))
    if flown.is_file():
        if flown.read_text() != plan:
            raise StepError(
                f"run: the plan {run} flew isn't {mission / 'mission.plan'}"
            )
    elif record.get("log") is not None:
        # A run that flew must still have the plan it flew. One that never logged
        # (the harness stopped during setup, maybe before copying the plan) is
        # INCONCLUSIVE whatever its plan.
        raise StepError(f"run: {flown}, the plan {run} flew, is missing")
    for kept, theirs in (
        (run / "start.xml", mission / "start.xml"),
        (run / "goal.xml", mission / "goal.xml"),
        (kept_settings(run), settings_path(mission)),
    ):
        if (
            kept is not None
            and kept.is_file()
            and kept.read_bytes() != theirs.read_bytes()
        ):
            raise StepError(f"run: {kept} isn't the mission's {theirs.name}")


def run_config(run, given):
    """The config to read and verify a run with: the px4.yaml it kept, if it did."""
    kept = run / "px4.yaml"
    if not kept.is_file():
        return given or DEFAULT_CONFIG
    if given is not None and Path(given).read_bytes() != kept.read_bytes():
        raise StepError(
            f"config: {run} was flown with its own px4.yaml, which differs from "
            f"{given}; leave out --config to use the run's"
        )
    return kept


def read(run, config_path):
    path = run / "readings.json"
    for done in (path, run / "verdict.json"):
        if done.exists():
            raise StepError(
                f"read: {done} exists; remove readings.json and verdict.json "
                "to read the run again"
            )
    try:
        readings = read_run(run, load_config(config_path))
    except (ReaderError, FileNotFoundError) as error:
        raise StepError(f"read: can't read the run: {error}") from error
    path.write_text(readings_text(readings))
    problem = readings.get("log_problem")
    print(f"read: {path}" + (f" ({problem})" if problem else ""))
    return path


def check(mission, readings, run, config_path):
    out = run / "verdict.json"
    # A run folder that keeps the mission's states and settings is verified from
    # those, so the verdict rests on what was flown. Otherwise, the mission folder.
    kept = kept_settings(run)
    use_kept = kept is not None and (run / "goal.xml").is_file()
    flown = kept if use_kept else settings_path(mission)
    args = [str(flown), str(readings), "--config", str(config_path)]
    if verify([*args, "--output", str(out)]) != 0:
        raise StepError("verify: the verifier stopped; its error is above")
    verdict = json.loads(out.read_text())
    print(f"verify: {out}: {verdict['verdict']}")
    for item in verdict["checks"]:
        where = f" {item['waypoint']}" if "waypoint" in item else ""
        print(f"  {item['check']}{where}: {item['verdict']} ({item['reason']})")
    return verdict


def kept_settings(run):
    """The settings a run folder kept, or None: settings.yaml, or for a run kept
    before that name was fixed, its one .yaml besides px4.yaml."""
    try:
        return settings_path(run)
    except StepError:
        return None


def settings_path(folder):
    """A folder's mission settings: settings.yaml in a run folder, else its one .yaml.
    A run folder's px4.yaml is the config it was flown with, not settings."""
    if (folder / KEPT_SETTINGS).is_file():
        return folder / KEPT_SETTINGS
    found = sorted(folder.glob("*.yaml"))
    if (folder / "run.json").is_file():  # a run folder: px4.yaml is its config
        found = [path for path in found if path.name != "px4.yaml"]
    if len(found) != 1:
        listed = ", ".join(path.name for path in found) or "none"
        raise StepError(f"{folder} should hold one settings file (.yaml), has {listed}")
    return found[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--mission", type=Path, help="an existing mission folder")
    where.add_argument("--template", type=Path, help="environment template (XML)")
    parser.add_argument("--settings", type=Path, help="mission settings (simple.yaml)")
    parser.add_argument("--out", type=Path, help="new mission folder to generate")
    parser.add_argument("--seed", type=int, help="random seed (drawn if omitted)")
    flight = parser.add_mutually_exclusive_group()
    flight.add_argument("--px4", type=Path, help="built PX4 checkout, to fly the plan")
    flight.add_argument("--run", type=Path, help="a run folder that was already flown")
    parser.add_argument("--run-id", default="R001", help="run folder name (--px4)")
    parser.add_argument(
        "--config", type=Path, help=f"platform config (default: {DEFAULT_CONFIG})"
    )
    args = parser.parse_args(argv)
    if args.template and not (args.settings and args.out):
        parser.error("--template needs --settings and --out")
    if not (args.template or args.mission or args.run):
        parser.error("give --template, --mission or --run")

    try:
        # A run given with --run is read and verified with the config it kept.
        config = run_config(args.run, args.config) if args.run else None
        config = config or args.config or DEFAULT_CONFIG
        if args.template:
            seed = args.seed if args.seed is not None else secrets.randbits(32)
            make_mission(args.template, args.settings, args.out, config, seed)
            mission = args.out
        else:
            # --run alone replays a run from the plan, states and settings it kept.
            seed, mission = args.seed, args.mission or args.run
        plan_path, expected_plan = plan(mission, config, write=args.run is None)
        if args.px4:
            run = fly(mission, plan_path, config, args.px4, args.run_id, seed)
        elif args.run:
            run = args.run
            match_run(mission, run, expected_plan)
        else:
            print("fly: no --px4 or --run given; stopping after the plan")
            return 2
        readings = read(run, config)
        check(mission, readings, run, config)
    except StepError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
