"""python -m log_reader RUN_FOLDER [--out PATH] [--config PATH]"""

import argparse
import sys
from pathlib import Path

from .readings import DEFAULT_CONFIG, ReaderError, load_config, read_run, readings_text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m log_reader", description=__doc__)
    parser.add_argument("run", type=Path, help="run folder with run.json")
    parser.add_argument(
        "--out", type=Path, help="where to write (default: RUN/readings.json)"
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="platform config"
    )
    args = parser.parse_args(argv)

    try:
        readings = read_run(args.run, load_config(args.config))
    except (ReaderError, FileNotFoundError) as error:
        print(f"can't read the run: {error}", file=sys.stderr)
        return 1
    out = args.out or args.run / "readings.json"
    out.write_text(readings_text(readings))
    check = readings.get("cross_check")
    note = f", cross-check {check['verdict']}" if check else ""
    print(f"wrote {out} ({len(readings['position'])} positions{note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
