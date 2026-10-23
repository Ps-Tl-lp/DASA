# How to use the mission verifier

The verifier compares a QGroundControl `.plan` (expected flight) with a PX4
`.ulg` log (recorded flight). It checks launch location, waypoint arrival in
order, altitude, and dwell time.

From the repository root, run:

```powershell
python verifier/verifier.py
```

## Terminal questions

| Question | What to enter |
| --- | --- |
| `QGroundControl .plan file path:` | Your mission plan, for example `missions/simple.plan`. |
| `PX4 .ulg log file path:` | Your recorded flight log, for example `"C:/Flight Logs/flight.ulg"`. |
| `Launch tolerance (m):` | Allowed distance from the planned home location at takeoff. |
| `Waypoint horizontal tolerance (m):` | Allowed horizontal distance from each waypoint. |
| `Altitude tolerance (m):` | Allowed distance above or below the target altitude. |

Paths can be absolute or relative to the folder where you run the command.
Spaces are allowed; surrounding quotes are optional. Use your actual log path.
The extracted mission requirements appear after the file-path questions.

## Buffer room

The three tolerances are your **buffer room**, all in meters. For example,
entering `2` for horizontal tolerance allows the vehicle to be within 2 meters
of a waypoint. Entering `1` for altitude tolerance allows 1 meter above or below
its target. These are examples; choose tolerances for your mission.

Dwell time comes from the plan. The vehicle must stay inside both the horizontal
and altitude buffers for that duration. Leaving the buffers or losing continuous
valid telemetry resets the dwell timer. The default maximum sample gap is 1 second.

## Results

The terminal shows each check and an overall result:

- **PASS (green), exit 0:** The selected requirements have sufficient evidence.
- **FAIL (red), exit 1:** Evidence shows a requirement was not met.
- **INCONCLUSIVE (yellow), exit 2:** Evidence is missing, invalid, or incomplete.
- **Couldn't run, exit 3:** Bad arguments, unreadable files, or an invalid/unsupported plan.

Only the four listed requirements are checked; this is not a full safety check.
