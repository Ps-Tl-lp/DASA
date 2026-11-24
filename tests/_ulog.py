"""Write tiny PX4 ULog files, so the log reader can be tested without real logs.

The ULog format (docs.px4.io/main/en/dev_log/ulog_file_format.html): a 16-byte header,
then messages, each a uint16 size, a one-letter type, and the payload.
  B  flag bits        F  a topic's format ("name:type field;type field;")
  P  a parameter      A  "this topic is logged under id N"     D  one sample of a topic
All little-endian, fields packed with no padding.
"""

import struct

_PACK = {"uint64_t": "Q", "float": "f", "double": "d", "bool": "?", "uint8_t": "B"}
_PARAM = {"int32_t": "i", "float": "f"}


def _message(kind, payload):
    return struct.pack("<HB", len(payload), ord(kind)) + payload


def write_ulog(path, topics, parameters=None, damaged=False):
    """Write a .ulg file.

    topics: {name: (fields, rows)}. fields is [(ulog type, field name), ...], starting
    with ("uint64_t", "timestamp"); rows is a list of tuples in that order.
    parameters: {name: int or float} (written as int32_t or float).
    damaged: put a message of size 0 and type 0 before the last sample. pyulog
    reports that as file corruption and skips ahead, so the last sample is lost.
    """
    out = bytearray(b"ULog\x01\x12\x35" + bytes([1]) + struct.pack("<Q", 0))
    out += _message("B", bytes(16) + struct.pack("<QQQ", 0, 0, 0))
    for name, (fields, _rows) in topics.items():
        spec = "".join(f"{t} {f};" for t, f in fields)
        out += _message("F", f"{name}:{spec}".encode())
    for name, value in (parameters or {}).items():
        kind = "int32_t" if isinstance(value, int) else "float"
        key = f"{kind} {name}".encode()
        out += _message(
            "P", bytes([len(key)]) + key + struct.pack("<" + _PARAM[kind], value)
        )
    for msg_id, name in enumerate(topics):
        out += _message("A", struct.pack("<BH", 0, msg_id) + name.encode())

    samples = []
    for msg_id, (fields, rows) in enumerate(topics.values()):
        layout = "<" + "".join(_PACK[t] for t, _ in fields)
        samples += [(row[0], msg_id, struct.pack(layout, *row)) for row in rows]
    ordered = sorted(samples, key=lambda s: (s[0], s[1]))
    for index, (_t, msg_id, payload) in enumerate(ordered):
        if damaged and index == len(ordered) - 1:
            out += struct.pack("<HB", 0, 0)
        out += _message("D", struct.pack("<H", msg_id) + payload)
    path.write_bytes(bytes(out))
    return path
