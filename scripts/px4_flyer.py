"""Bounded MAVLink mission execution for local PX4 SITL."""

import math
import struct
import time


class RunError(Exception):
    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason


def parameter_value(message):
    if message.param_type == 6:
        return struct.unpack("<i", struct.pack("<f", message.param_value))[0]
    if message.param_type == 5:
        return struct.unpack("<I", struct.pack("<f", message.param_value))[0]
    if message.param_type == 9:
        return message.param_value
    raise RunError("sim_setup", f"unsupported parameter type {message.param_type}")


class Flyer:
    def __init__(self, connection, event, health, setup_timeout=60):
        self.link = connection
        self.event = event
        self.health = health
        self.setup_timeout = setup_timeout
        self.armed = False
        self.mode = None
        self.airborne = False
        self.last_heartbeat = 0
        self.last_sent = 0

    def receive(self):
        self.health()
        now = time.monotonic()
        if now - self.last_sent >= 1:
            self.link.mav.heartbeat_send(6, 8, 0, 0, 4)
            self.last_sent = now
        msg = self.link.recv_match(blocking=True, timeout=0.2)
        if msg is None or msg.get_srcSystem() != 1 or msg.get_srcComponent() != 1:
            return None
        kind = msg.get_type()
        if kind == "HEARTBEAT":
            if msg.autopilot != 12:
                raise RunError("no_connection", "expected PX4 SITL")
            self.armed = bool(msg.base_mode & 128)
            self.mode = (msg.custom_mode >> 16) & 0xFFFF
            self.last_heartbeat = now
        elif kind == "EXTENDED_SYS_STATE":
            self.airborne = msg.landed_state == 2
        elif kind == "STATUSTEXT":
            self.event("px4_status", text=msg.text)
        return msg

    def wait(self, predicate, seconds, reason):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            msg = self.receive()
            if predicate(msg):
                return msg
        raise RunError(reason, f"wait exceeded {seconds} wall seconds")

    def command(self, command, *params, reason="mission_starts"):
        self.link.mav.command_long_send(
            1, 1, command, 0, *(list(params) + [0] * (7 - len(params)))
        )
        msg = self.wait(
            lambda m: (
                m is not None and m.get_type() == "COMMAND_ACK" and m.command == command
            ),
            10,
            reason,
        )
        if msg.result != 0:
            raise RunError(
                reason, f"command {command} rejected/in progress: {msg.result}"
            )

    def parameters(self, settings):
        actual = {}
        for name, value in settings.items():
            key = name.encode("ascii")
            self.link.mav.param_request_read_send(1, 1, key, -1)

            def match(m, expected=name):
                return (
                    m is not None
                    and m.get_type() == "PARAM_VALUE"
                    and m.param_id == expected
                )

            msg = self.wait(match, 10, "sim_setup")
            if msg.param_type == 6:
                encoded = struct.unpack("<f", struct.pack("<i", int(value)))[0]
            elif msg.param_type == 9:
                encoded = float(value)
            else:
                raise RunError("sim_setup", f"unsupported parameter type for {name}")
            self.link.mav.param_set_send(1, 1, key, encoded, msg.param_type)
            msg = self.wait(match, 10, "sim_setup")
            actual[name] = parameter_value(msg)
            if not math.isclose(actual[name], value, rel_tol=1e-5, abs_tol=1e-5):
                raise RunError("sim_setup", f"parameter readback mismatch: {name}")
        return actual

    def upload(self, items):
        self.link.mav.mission_count_send(1, 1, len(items), 0)
        sent = set()

        def handle(msg):
            if msg is None:
                return False
            kind = msg.get_type()
            if kind in ("MISSION_REQUEST_INT", "MISSION_REQUEST"):
                seq = msg.seq
                if seq >= len(items):
                    raise RunError("upload_failed", "invalid requested mission index")
                item = items[seq]
                p = [float("nan") if v is None else v for v in item["params"]]
                frame = item["frame"]
                if kind == "MISSION_REQUEST_INT":
                    frame = {0: 5, 3: 6}.get(frame, frame)
                    self.link.mav.mission_item_int_send(
                        1,
                        1,
                        seq,
                        frame,
                        item["command"],
                        int(seq == 0),
                        1,
                        *p[:4],
                        round(p[4] * 1e7),
                        round(p[5] * 1e7),
                        p[6],
                        0,
                    )
                else:
                    self.link.mav.mission_item_send(
                        1,
                        1,
                        seq,
                        frame,
                        item["command"],
                        int(seq == 0),
                        1,
                        *p,
                        0,
                    )
                sent.add(seq)
            elif kind == "MISSION_ACK":
                if msg.type != 0 or len(sent) != len(items):
                    raise RunError(
                        "upload_failed", f"mission ACK {msg.type}, sent {len(sent)}"
                    )
                return True
            return False

        self.wait(handle, 30, "upload_failed")

    def fly(self, items, settings, timeout):
        self.wait(
            lambda _: self.last_heartbeat > 0, self.setup_timeout, "no_connection"
        )
        actual = self.parameters(settings)
        self.event("parameters", values=actual)
        self.upload(items)
        self.event("upload_accepted", items=len(items))
        self.command(511, 245, 100000, reason="sim_setup")
        self.command(176, 1, 4, 4)
        # Retry ordinary arming while preflight sensors settle. Never force-arm.
        deadline = time.monotonic() + self.setup_timeout
        while True:
            try:
                self.command(400, 1, reason="can_arm")
                break
            except RunError as exc:
                if exc.reason != "can_arm" or time.monotonic() >= deadline:
                    raise
        self.wait(
            lambda _: self.armed and self.mode == (4 | (4 << 8)), 15, "mission_starts"
        )
        started = time.monotonic()
        self.event("mission_started", timeout_wall_s=timeout)
        took_off = False
        while time.monotonic() - started < timeout:
            self.receive()
            took_off = took_off or self.airborne
            if time.monotonic() - self.last_heartbeat > 10:
                raise RunError("no_connection", "heartbeat lost during flight")
            if not self.armed:
                if not took_off:
                    raise RunError(
                        "no_takeoff", "disarmed without observed airborne state"
                    )
                self.event("disarmed")
                return actual
        raise RunError(
            "timeout", f"no disarm within {timeout} wall seconds of mission start"
        )
