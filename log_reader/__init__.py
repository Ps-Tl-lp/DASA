"""The log reader: a run's PX4 log and Gazebo recording to readings.json.

    python -m log_reader RUN_FOLDER [--out PATH] [--config PATH]

RUN_FOLDER holds the run's run.json, which names its .ulg log and, for a recorded run,
its Gazebo pose recording. The rows come from platform_configs/px4.yaml (`readings`,
`log_only_readings`, `time_zero_topics`, `cross_check`). It doesn't need the mission
and judges nothing: the verifier does that.
"""

from .readings import ReaderError, landed, rate_of, read_run, readings_text

__all__ = ["ReaderError", "landed", "rate_of", "read_run", "readings_text"]
