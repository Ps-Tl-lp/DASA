# ADR 0006: local simulation harness and independent pose recording

Status: proposed implementation, authorized by Prithvi on 2026-11-23.

The harness runs on Linux/WSL with the existing PX4/Gazebo installation. It reads
the shared config and start state, starts the recorder before PX4, flies a supplied
plan and writes the documented run.json. The flight deadline is 300 wall-clock
seconds from confirmed mission start, or the configured flight_timeout_s.
Timeout produces run_status=inconclusive and reason=timeout. This does not set
the mission verdict. No recovery command is sent after the deadline.

Gazebo Transport 13 / Messages 10 (Harmonic), PyYAML and pymavlink are runtime
prerequisites. They are imported lazily and are not added to the CI dependencies.
Each run uses a unique Gazebo partition and PX4 working directory. Only owned
process groups are stopped. Raw evidence stays under runs/ outside git.

The recorder writes simulator time and ENU model pose directly from Pose_V,
plus topic publisher addresses/types and diagnostic info. It does not convert
poses into mission readings or evaluate the cross-check. The log reader owns that.

The recorder and PX4 currently share a host/account. Isolation against a malicious
autopilot remains the separate-container follow-up discussed in PR 28.
