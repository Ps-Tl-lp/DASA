"""Read the topics and parameters we need from a PX4 .ulg log, using pyulog.

pyulog is PX4's own ULog parser. It gives each logged topic as columns of numbers,
with a `timestamp` column in microseconds since PX4 started. This module turns that
into plain Python lists, so the rest of the log reader is ordinary Python.
"""

import struct

from pyulog import ULog, ULogException


class MissingField(Exception):
    """A topic the log has, without a field the config names (another PX4 build?)."""


class UnreadableLog(Exception):
    """A log pyulog can't open at all, such as one whose header is damaged."""


class Log:
    """The parts of one .ulg file the log reader asked for."""

    def __init__(self, path, topics):
        # Only parse the topics we need: a 4x flight log has hundreds of topics.
        try:
            ulog = ULog(str(path), message_name_filter_list=sorted(topics))
        except (
            ULogException,
            ValueError,
            TypeError,
            IndexError,
            struct.error,
        ) as error:
            # pyulog's own errors for a file it can't parse.
            raise UnreadableLog(
                f"the log {path.name} can't be read: {error}"
            ) from error
        self.columns = {}  # topic -> {field: [values]}
        self.types = {}  # (topic, field) -> the field's ULog type, e.g. "bool", "float"
        for data in ulog.data_list:
            if data.multi_id != 0:
                continue  # a second instance of the same topic; ours have one
            self.columns[data.name] = {f: v.tolist() for f, v in data.data.items()}
            for field in data.field_data:
                self.types[(data.name, field.field_name)] = field.type_str
        # Parameters as they were when logging started.
        self.parameters = dict(ulog.initial_parameters)
        # pyulog skips what it can't parse and only flags it. What is left can still
        # look like a good flight, so the reader says so (R5: a corrupted log is
        # INCONCLUSIVE).
        self.problem = None
        if ulog.file_corruption:
            self.problem = "the log is damaged: pyulog skipped data it couldn't read"

    def has(self, topic):
        return topic in self.columns

    def timestamps(self, topic):
        """The topic's sample times in microseconds, or [] if it wasn't logged."""
        return self.columns.get(topic, {}).get("timestamp", [])

    def series(self, topic, field):
        """[(timestamp_us, value), ...] for one field, with bools as True/False."""
        columns = self.columns.get(topic)
        if columns is None:
            return []
        if field not in columns:
            raise MissingField(f"the log's {topic} has no field {field}")
        values = columns[field]
        if self.types.get((topic, field)) == "bool":
            values = [bool(v) for v in values]  # pyulog stores bools as 0/1 integers
        return list(zip(columns["timestamp"], values, strict=True))
